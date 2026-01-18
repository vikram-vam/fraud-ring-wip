"""
Fraud Detection Algorithms for Insurance Network Analysis
Identifies suspicious communities and patterns in the graph

Visual Hierarchy:
- Confirmed Fraud (is_fraud=true): RED - Ground truth, labeled data
- Suspicious (suspicious=true): ORANGE spectrum - Algorithm-detected, requires investigation

Detection algorithms exclude entities already labeled as fraud to avoid redundancy.
"""

from neo4j import GraphDatabase
import streamlit as st


class FraudDetector:
    def __init__(self):
        """
        Initialize fraud detector with Neo4j connection from Streamlit secrets.
        """
        try:
            uri = st.secrets["neo4j"]["uri"]
            user = st.secrets["neo4j"]["user"]
            password = st.secrets["neo4j"]["password"]
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Neo4j. Ensure secrets.toml is configured: {e}")
    
    def close(self):
        self.driver.close()
    
    def clear_previous_detections(self):
        """
        Clear all previous detection flags before running new detection.
        Ensures fresh results based on current parameters.
        
        Note: This only clears 'suspicious' flags, NOT 'is_fraud' labels.
        """
        print("\n🧹 Clearing previous detection flags...")
        
        with self.driver.session() as session:
            # Clear suspicious flags
            result1 = session.run("""
                MATCH (n) WHERE n.suspicious = true
                REMOVE n.suspicious, n.suspicion_type, n.suspicion_score
                RETURN count(n) as count
            """)
            flagged = result1.single()["count"]
            
            # Clear degree centrality
            result2 = session.run("""
                MATCH (n) WHERE n.degree_centrality IS NOT NULL
                REMOVE n.degree_centrality
                RETURN count(n) as count
            """)
            centrality = result2.single()["count"]
            
            # Remove suspicious relationships
            result3 = session.run("""
                MATCH ()-[r:SUSPICIOUS_RELATIONSHIP]->()
                DELETE r
                RETURN count(r) as count
            """)
            rels = result3.single()["count"]
            
            print(f"   ✓ Cleared {flagged} flagged entities")
            print(f"   ✓ Removed centrality from {centrality} nodes")
            print(f"   ✓ Deleted {rels} suspicious relationships")
    
    def detect_medical_mills(self, min_claims=5, min_avg_amount=15000):
        """
        Detect potential medical mills - providers with suspiciously high claim volumes
        and elevated average claim amounts.
        
        Flags: MedicalProvider + associated Claims
        Excludes: Entities already labeled as fraud (is_fraud=true)
        
        Args:
            min_claims: Minimum number of claims to flag a provider
            min_avg_amount: Minimum average claim amount threshold
        """
        print("\n🔍 Detecting Medical Mills...")
        
        with self.driver.session() as session:
            # Query excludes providers already marked as fraud
            query = """
            MATCH (c:Claim)-[:TREATED_AT]->(m:MedicalProvider)
            WHERE c.is_fraud = false 
              AND (m.is_fraud IS NULL OR m.is_fraud = false)
            WITH m, collect(c) as claims, count(c) as claim_count
            WHERE claim_count >= $min_claims
            WITH m, claims, claim_count,
                 [c IN claims | c.claim_amount] as amounts
            WITH m, claims, claim_count, amounts,
                 reduce(sum = 0.0, amount IN amounts | sum + amount) / claim_count as avg_amount
            WHERE avg_amount > $min_avg_amount
            RETURN m.id as provider_id, 
                   m.name as provider_name,
                   claim_count,
                   avg_amount,
                   [c IN claims | c.id] as claim_ids
            ORDER BY claim_count DESC, avg_amount DESC
            """
            
            result = session.run(query, min_claims=min_claims, min_avg_amount=min_avg_amount)
            mills = []
            
            for record in result:
                mills.append({
                    'provider_id': record['provider_id'],
                    'provider_name': record['provider_name'],
                    'claim_count': record['claim_count'],
                    'avg_amount': round(record['avg_amount'], 2),
                    'claim_ids': record['claim_ids'],
                    'fraud_type': 'Medical Mill',
                    'suspicion_score': min(100, record['claim_count'] * 8 + int(record['avg_amount'] / 1000))
                })
            
            # Flag suspicious providers AND their claims (excluding known fraud)
            if mills:
                total_claims_flagged = 0
                for mill in mills:
                    result = session.run("""
                        MATCH (m:MedicalProvider {id: $provider_id})
                        WHERE m.is_fraud IS NULL OR m.is_fraud = false
                        SET m.suspicious = true,
                            m.suspicion_type = 'Medical Mill',
                            m.suspicion_score = $score
                        WITH m
                        MATCH (c:Claim)-[:TREATED_AT]->(m)
                        WHERE c.is_fraud = false
                        SET c.suspicious = true,
                            c.suspicion_type = 'Medical Mill',
                            c.suspicion_score = toInteger($score * 0.8)
                        RETURN count(c) as claims_flagged
                        """,
                        provider_id=mill['provider_id'],
                        score=mill['suspicion_score'])
                    
                    total_claims_flagged += result.single()['claims_flagged']
                
                print(f"   ✓ Found {len(mills)} suspicious medical providers")
                print(f"   ✓ Flagged {total_claims_flagged} associated claims")
                for mill in mills[:5]:
                    print(f"      - {mill['provider_name']}: {mill['claim_count']} claims, ${mill['avg_amount']:,.2f} avg")
            else:
                print("   ✓ No medical mills detected")
            
            return mills
    
    def detect_bodyshop_kickbacks(self, min_shared_claims=3):
        """
        Detect body shop kickback schemes - attorneys consistently referring to same body shop.
        
        Flags: Attorney + BodyShop + Claims involving both
        Excludes: Entities already labeled as fraud (is_fraud=true)
        
        Args:
            min_shared_claims: Minimum shared claims between attorney-bodyshop pair
        """
        print("\n🔍 Detecting Body Shop Kickbacks...")
        
        with self.driver.session() as session:
            # Query excludes attorneys/bodyshops already marked as fraud
            query = """
            MATCH (c:Claim)-[:REPRESENTED_BY]->(a:Attorney)
            MATCH (c)-[:REPAIRED_AT]->(b:BodyShop)
            WHERE c.is_fraud = false
              AND (a.is_fraud IS NULL OR a.is_fraud = false)
              AND (b.is_fraud IS NULL OR b.is_fraud = false)
            WITH a, b, count(c) as shared_claims, collect(c.id) as claim_ids
            WHERE shared_claims >= $min_shared_claims
            RETURN a.id as attorney_id,
                   a.name as attorney_name,
                   b.id as bodyshop_id,
                   b.name as bodyshop_name,
                   shared_claims,
                   claim_ids
            ORDER BY shared_claims DESC
            """
            
            result = session.run(query, min_shared_claims=min_shared_claims)
            kickbacks = []
            
            for record in result:
                kickbacks.append({
                    'attorney_id': record['attorney_id'],
                    'attorney_name': record['attorney_name'],
                    'bodyshop_id': record['bodyshop_id'],
                    'bodyshop_name': record['bodyshop_name'],
                    'shared_claims': record['shared_claims'],
                    'claim_ids': record['claim_ids'],
                    'fraud_type': 'Body Shop Kickback',
                    'suspicion_score': min(100, record['shared_claims'] * 15)
                })
            
            # Flag suspicious attorney, bodyshop, AND their shared claims (excluding known fraud)
            if kickbacks:
                total_claims_flagged = 0
                for kb in kickbacks:
                    result = session.run("""
                        MATCH (a:Attorney {id: $attorney_id})
                        WHERE a.is_fraud IS NULL OR a.is_fraud = false
                        MATCH (b:BodyShop {id: $bodyshop_id})
                        WHERE b.is_fraud IS NULL OR b.is_fraud = false
                        SET a.suspicious = true,
                            a.suspicion_type = 'Kickback Scheme',
                            a.suspicion_score = $score,
                            b.suspicious = true,
                            b.suspicion_type = 'Kickback Scheme',
                            b.suspicion_score = $score
                        MERGE (a)-[r:SUSPICIOUS_RELATIONSHIP]->(b)
                        SET r.shared_claims = $shared_claims
                        WITH a, b
                        MATCH (c:Claim)-[:REPRESENTED_BY]->(a)
                        MATCH (c)-[:REPAIRED_AT]->(b)
                        WHERE c.is_fraud = false
                        SET c.suspicious = true,
                            c.suspicion_type = 'Kickback Scheme',
                            c.suspicion_score = toInteger($score * 0.8)
                        RETURN count(c) as claims_flagged
                        """,
                        attorney_id=kb['attorney_id'],
                        bodyshop_id=kb['bodyshop_id'],
                        score=kb['suspicion_score'],
                        shared_claims=kb['shared_claims'])
                    
                    total_claims_flagged += result.single()['claims_flagged']
                
                print(f"   ✓ Found {len(kickbacks)} suspicious attorney-bodyshop relationships")
                print(f"   ✓ Flagged {total_claims_flagged} associated claims")
                for kb in kickbacks[:5]:
                    print(f"      - {kb['attorney_name']} → {kb['bodyshop_name']}: {kb['shared_claims']} claims")
            else:
                print("   ✓ No kickback schemes detected")
            
            return kickbacks
    
    def detect_staged_accidents(self, min_shared_claims=2):
        """
        Detect staged accidents - same people appearing in multiple claims together.
        
        Flags: Person (conspirators) + their shared Claims
        Excludes: Entities already labeled as fraud (is_fraud=true)
        
        Args:
            min_shared_claims: Minimum claims two people must share to be flagged
        """
        print("\n🔍 Detecting Staged Accidents...")
        
        with self.driver.session() as session:
            # Query excludes persons already marked as fraud
            query = """
            MATCH (c:Claim)-[:FILED_BY|WITNESSED_BY]->(p:Person)
            WHERE c.is_fraud = false 
              AND c.claim_type = 'Auto'
              AND (p.is_fraud IS NULL OR p.is_fraud = false)
            WITH p, collect(DISTINCT c) as claims
            WHERE size(claims) >= $min_shared_claims
            UNWIND claims as claim1
            UNWIND claims as claim2
            WITH p, claim1, claim2
            WHERE id(claim1) < id(claim2)
            
            MATCH (claim1)-[:FILED_BY|WITNESSED_BY]->(other:Person)
            MATCH (claim2)-[:FILED_BY|WITNESSED_BY]->(other)
            WHERE p.id <> other.id
              AND (other.is_fraud IS NULL OR other.is_fraud = false)
            
            WITH p, other, collect(DISTINCT claim1.id) + collect(DISTINCT claim2.id) as shared_claim_ids
            WITH p, other, shared_claim_ids, size(shared_claim_ids) as shared_count
            WHERE shared_count >= $min_shared_claims
            
            WITH collect({person1: p.id, person2: other.id, shared_claims: shared_count, claim_ids: shared_claim_ids}) as pairs
            UNWIND pairs as pair
            RETURN pair.person1 as person1_id,
                   pair.person2 as person2_id,
                   pair.shared_claims as shared_claims,
                   pair.claim_ids as claim_ids
            ORDER BY pair.shared_claims DESC
            LIMIT 50
            """
            
            result = session.run(query, min_shared_claims=min_shared_claims)
            
            staged = []
            seen_pairs = set()
            
            for record in result:
                p1 = record['person1_id']
                p2 = record['person2_id']
                pair_key = tuple(sorted([p1, p2]))
                
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    staged.append({
                        'person1_id': p1,
                        'person2_id': p2,
                        'shared_claims': record['shared_claims'],
                        'claim_ids': list(set(record['claim_ids'])),  # Dedupe
                        'fraud_type': 'Staged Accident',
                        'suspicion_score': min(100, record['shared_claims'] * 25)
                    })
            
            # Flag suspicious people AND their shared claims (excluding known fraud)
            if staged:
                suspicious_people = set()
                claims_flagged = set()
                
                for accident in staged:
                    score = accident['suspicion_score']
                    
                    # Flag the people (only if not already known fraud)
                    for person_id in [accident['person1_id'], accident['person2_id']]:
                        suspicious_people.add(person_id)
                        session.run("""
                            MATCH (p:Person {id: $person_id})
                            WHERE p.is_fraud IS NULL OR p.is_fraud = false
                            SET p.suspicious = true,
                                p.suspicion_type = 'Staged Accident',
                                p.suspicion_score = $score
                            """,
                            person_id=person_id,
                            score=score)
                    
                    # Flag the shared claims (only if not already known fraud)
                    for claim_id in accident['claim_ids']:
                        if claim_id not in claims_flagged:
                            claims_flagged.add(claim_id)
                            session.run("""
                                MATCH (c:Claim {id: $claim_id})
                                WHERE c.is_fraud = false
                                SET c.suspicious = true,
                                    c.suspicion_type = 'Staged Accident',
                                    c.suspicion_score = toInteger($score * 0.8)
                                """,
                                claim_id=claim_id,
                                score=score)
                
                print(f"   ✓ Found {len(staged)} suspicious person pairs in multiple claims")
                print(f"   ✓ Flagged {len(suspicious_people)} individuals")
                print(f"   ✓ Flagged {len(claims_flagged)} associated claims")
                for acc in staged[:5]:
                    print(f"      - {acc['person1_id']} & {acc['person2_id']}: {acc['shared_claims']} shared claims")
            else:
                print("   ✓ No staged accidents detected")
            
            return staged
    
    def detect_phantom_passengers(self, min_connections=3):
        """
        Detect phantom passengers - people with suspiciously high connections 
        to multiple claimants via KNOWS relationships.
        
        Flags: Person (phantoms) + their filed Claims
        Excludes: Entities already labeled as fraud (is_fraud=true)
        
        Args:
            min_connections: Minimum KNOWS connections to flag as suspicious
        """
        print("\n🔍 Detecting Phantom Passengers...")
        
        with self.driver.session() as session:
            # Query excludes persons already marked as fraud
            query = """
            MATCH (p:Person:Claimant)-[:KNOWS]-(connected:Person:Claimant)
            WHERE (p.is_fraud IS NULL OR p.is_fraud = false)
              AND (connected.is_fraud IS NULL OR connected.is_fraud = false)
            WITH connected, collect(DISTINCT p) as claimants, count(DISTINCT p) as connection_count
            WHERE connection_count >= $min_connections
            OPTIONAL MATCH (connected)-[:FILED_BY]-(c:Claim)
            WHERE c.is_fraud = false
            WITH connected, claimants, connection_count, collect(c) as claims
            WHERE size(claims) > 0
            WITH connected, connection_count, size(claims) as claim_count,
                 [claim IN claims | claim.id] as claim_ids,
                 [claimant IN claimants | claimant.id] as claimant_ids
            WHERE claim_count >= $min_connections
            RETURN connected.id as person_id,
                   connected.name as person_name,
                   connection_count,
                   claim_count,
                   claim_ids,
                   claimant_ids
            ORDER BY connection_count DESC, claim_count DESC
            """
            
            result = session.run(query, min_connections=min_connections)
            phantoms = []
            
            for record in result:
                phantoms.append({
                    'person_id': record['person_id'],
                    'person_name': record['person_name'],
                    'connection_count': record['connection_count'],
                    'claim_count': record['claim_count'],
                    'claim_ids': record['claim_ids'],
                    'claimant_ids': record['claimant_ids'],
                    'fraud_type': 'Phantom Passenger',
                    'suspicion_score': min(100, record['connection_count'] * 20)
                })
            
            # Flag suspicious phantom passengers AND their claims (excluding known fraud)
            if phantoms:
                total_claims_flagged = 0
                for phantom in phantoms:
                    result = session.run("""
                        MATCH (p:Person {id: $person_id})
                        WHERE p.is_fraud IS NULL OR p.is_fraud = false
                        SET p.suspicious = true,
                            p.suspicion_type = 'Phantom Passenger',
                            p.suspicion_score = $score
                        WITH p
                        MATCH (c:Claim)-[:FILED_BY]->(p)
                        WHERE c.is_fraud = false
                        SET c.suspicious = true,
                            c.suspicion_type = 'Phantom Passenger',
                            c.suspicion_score = toInteger($score * 0.8)
                        RETURN count(c) as claims_flagged
                        """,
                        person_id=phantom['person_id'],
                        score=phantom['suspicion_score'])
                    
                    total_claims_flagged += result.single()['claims_flagged']
                
                print(f"   ✓ Found {len(phantoms)} suspicious phantom passengers")
                print(f"   ✓ Flagged {total_claims_flagged} associated claims")
                for phantom in phantoms[:5]:
                    print(f"      - {phantom['person_name']}: {phantom['claim_count']} claims, {phantom['connection_count']} connections")
            else:
                print("   ✓ No phantom passengers detected")
            
            return phantoms
    
    def detect_adjuster_collusion(self, min_shared_claims=4):
        """
        Detect adjuster-provider collusion - adjusters consistently handling claims 
        from specific medical providers (kickback arrangement).
        
        Flags: Adjuster + MedicalProvider + shared Claims
        Excludes: Entities already labeled as fraud (is_fraud=true)
        
        Args:
            min_shared_claims: Minimum shared claims between adjuster-provider pair
        """
        print("\n🔍 Detecting Adjuster-Provider Collusion...")
        
        with self.driver.session() as session:
            # Query finds adjuster-provider pairs with high claim overlap
            query = """
            MATCH (c:Claim)-[:HANDLED_BY]->(adj:Person:Adjuster)
            MATCH (c)-[:TREATED_AT]->(m:MedicalProvider)
            WHERE c.is_fraud = false
              AND (adj.is_fraud IS NULL OR adj.is_fraud = false)
              AND (m.is_fraud IS NULL OR m.is_fraud = false)
            WITH adj, m, count(c) as shared_claims, collect(c.id) as claim_ids
            WHERE shared_claims >= $min_shared_claims
            RETURN adj.id as adjuster_id,
                   adj.name as adjuster_name,
                   m.id as provider_id,
                   m.name as provider_name,
                   shared_claims,
                   claim_ids
            ORDER BY shared_claims DESC
            """
            
            result = session.run(query, min_shared_claims=min_shared_claims)
            collusions = []
            
            for record in result:
                collusions.append({
                    'adjuster_id': record['adjuster_id'],
                    'adjuster_name': record['adjuster_name'],
                    'provider_id': record['provider_id'],
                    'provider_name': record['provider_name'],
                    'shared_claims': record['shared_claims'],
                    'claim_ids': record['claim_ids'],
                    'fraud_type': 'Adjuster-Provider Collusion',
                    'suspicion_score': min(100, record['shared_claims'] * 12)
                })
            
            # Flag suspicious adjuster, provider, AND their shared claims
            if collusions:
                total_claims_flagged = 0
                for col in collusions:
                    result = session.run("""
                        MATCH (adj:Person:Adjuster {id: $adjuster_id})
                        WHERE adj.is_fraud IS NULL OR adj.is_fraud = false
                        MATCH (m:MedicalProvider {id: $provider_id})
                        WHERE m.is_fraud IS NULL OR m.is_fraud = false
                        SET adj.suspicious = true,
                            adj.suspicion_type = 'Adjuster-Provider Collusion',
                            adj.suspicion_score = $score,
                            m.suspicious = true,
                            m.suspicion_type = 'Adjuster-Provider Collusion',
                            m.suspicion_score = $score
                        MERGE (adj)-[r:SUSPICIOUS_RELATIONSHIP]->(m)
                        SET r.shared_claims = $shared_claims
                        WITH adj, m
                        MATCH (c:Claim)-[:HANDLED_BY]->(adj)
                        MATCH (c)-[:TREATED_AT]->(m)
                        WHERE c.is_fraud = false
                        SET c.suspicious = true,
                            c.suspicion_type = 'Adjuster-Provider Collusion',
                            c.suspicion_score = toInteger($score * 0.8)
                        RETURN count(c) as claims_flagged
                        """,
                        adjuster_id=col['adjuster_id'],
                        provider_id=col['provider_id'],
                        score=col['suspicion_score'],
                        shared_claims=col['shared_claims'])
                    
                    total_claims_flagged += result.single()['claims_flagged']
                
                print(f"   ✓ Found {len(collusions)} suspicious adjuster-provider relationships")
                print(f"   ✓ Flagged {total_claims_flagged} associated claims")
                for col in collusions[:5]:
                    print(f"      - {col['adjuster_name']} ↔ {col['provider_name']}: {col['shared_claims']} claims")
            else:
                print("   ✓ No adjuster-provider collusion detected")
            
            return collusions

    def calculate_network_metrics(self):
        """
        Calculate network centrality metrics to identify key fraud nodes.
        Only calculates for non-fraud entities.
        """
        print("\n📊 Calculating Network Metrics...")
        
        with self.driver.session() as session:
            # Degree centrality - find highly connected nodes (exclude known fraud)
            result = session.run("""
                MATCH (n)
                WHERE (n.is_fraud IS NULL OR n.is_fraud = false)
                WITH n, COUNT { (n)--() } as degree
                WHERE degree > 5
                SET n.degree_centrality = degree
                RETURN labels(n)[0] as node_type, count(n) as count, avg(degree) as avg_degree
                """)
            
            print("\n   High-degree nodes (potential fraud hubs):")
            for record in result:
                print(f"      - {record['node_type']}: {record['count']} nodes, avg degree {record['avg_degree']:.2f}")
            
            # Suspicious nodes summary
            result = session.run("""
                MATCH (n)
                WHERE n.suspicious = true
                RETURN labels(n)[0] as node_type, 
                       n.suspicion_type as fraud_type,
                       count(n) as suspicious_count
                ORDER BY suspicious_count DESC
                """)
            
            print("\n   Suspicious nodes by type:")
            for record in result:
                print(f"      - {record['node_type']} ({record['fraud_type']}): {record['suspicious_count']}")
    
    def get_suspicious_communities(self):
        """
        Get all flagged suspicious communities for visualization.
        Returns only suspicious entities, not confirmed fraud.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n)
                WHERE n.suspicious = true
                RETURN n.id as id,
                       labels(n) as labels,
                       n.name as name,
                       n.suspicion_type as fraud_type,
                       n.suspicion_score as score
                ORDER BY n.suspicion_score DESC
                """)
            
            communities = []
            for record in result:
                communities.append({
                    'id': record['id'],
                    'type': record['labels'][0] if record['labels'] else 'Unknown',
                    'name': record['name'],
                    'fraud_type': record['fraud_type'],
                    'score': record['score']
                })
            
            return communities
    
    def run_all_detections(self, min_claims=5, min_shared_claims=3,
                           min_staged_claims=2, min_connections=3,
                           min_adjuster_collusion=4):
        """
        Run all fraud detection algorithms with configurable thresholds.
        Automatically clears previous detection flags before running.
        
        Note: Detection algorithms exclude entities already labeled as fraud (is_fraud=true)
        to avoid redundant flagging and maintain clear visual hierarchy.
        
        Args:
            min_claims: Threshold for medical mill detection
            min_shared_claims: Threshold for kickback detection
            min_staged_claims: Threshold for staged accident detection
            min_connections: Threshold for phantom passenger detection
        """
        print("=" * 60)
        print("FRAUD DETECTION ANALYSIS")
        print("=" * 60)
        print(f"Parameters: min_claims={min_claims}, min_shared={min_shared_claims}, "
              f"min_staged={min_staged_claims}, min_connections={min_connections}, "
              f"min_adjuster_collusion={min_adjuster_collusion}")
        print("\nNote: Excluding entities already labeled as confirmed fraud")
        
        # Clear previous detections first
        self.clear_previous_detections()
        
        results = {}
        
        # Run each detection algorithm with passed parameters
        results['medical_mills'] = self.detect_medical_mills(min_claims=min_claims)
        results['kickbacks'] = self.detect_bodyshop_kickbacks(min_shared_claims=min_shared_claims)
        results['staged_accidents'] = self.detect_staged_accidents(min_shared_claims=min_staged_claims)
        results['phantom_passengers'] = self.detect_phantom_passengers(min_connections=min_connections)
        results['adjuster_collusion'] = self.detect_adjuster_collusion(min_shared_claims=min_adjuster_collusion)
        # Calculate network metrics
        self.calculate_network_metrics()
        
        # Get summary
        communities = self.get_suspicious_communities()
        
        print("\n" + "=" * 60)
        print("DETECTION SUMMARY")
        print("=" * 60)
        print(f"Total suspicious entities flagged: {len(communities)}")
        print(f"  Medical Mills: {len(results['medical_mills'])} providers")
        print(f"  Kickback Schemes: {len(results['kickbacks'])} attorney-bodyshop pairs")
        print(f"  Staged Accidents: {len(results['staged_accidents'])} person pairs")
        print(f"  Phantom Passengers: {len(results['phantom_passengers'])} individuals")
        print(f"  Adjuster Collusion: {len(results['adjuster_collusion'])} adjuster-provider pairs")
        
        # Count flagged claims vs other entities
        claim_count = sum(1 for c in communities if c['type'] == 'Claim')
        entity_count = len(communities) - claim_count
        print(f"\n  Breakdown:")
        print(f"    - Suspicious Entities: {entity_count}")
        print(f"    - Suspicious Claims: {claim_count}")
        
        return results


if __name__ == "__main__":
    print("This module is designed to run within Streamlit.")
    print("Run: streamlit run app.py")