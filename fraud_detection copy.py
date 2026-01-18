"""
Fraud Detection Algorithms for Insurance Network Analysis
Identifies suspicious communities and patterns in the graph
"""

from neo4j import GraphDatabase
import pandas as pd
from collections import defaultdict
import json

class FraudDetector:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def detect_medical_mills(self, min_claims=5, threshold_days=180):
        """
        Detect potential medical mills - providers with suspiciously high claim volumes
        """
        print("\n🔍 Detecting Medical Mills...")
        
        with self.driver.session() as session:
            query = """
            MATCH (c:Claim)-[:TREATED_AT]->(m:MedicalProvider)
            WHERE c.is_fraud = false
            WITH m, collect(c) as claims, count(c) as claim_count
            WHERE claim_count >= $min_claims
            WITH m, claims, claim_count,
                 [c IN claims | c.claim_date] as dates,
                 [c IN claims | c.claim_amount] as amounts
            WITH m, claims, claim_count, dates, amounts,
                 reduce(sum = 0.0, amount IN amounts | sum + amount) / claim_count as avg_amount
            WHERE avg_amount > 20000
            RETURN m.id as provider_id, 
                   m.name as provider_name,
                   claim_count,
                   avg_amount,
                   [c IN claims | c.id] as claim_ids
            ORDER BY claim_count DESC, avg_amount DESC
            """
            
            result = session.run(query, min_claims=min_claims)
            mills = []
            
            for record in result:
                mills.append({
                    'provider_id': record['provider_id'],
                    'provider_name': record['provider_name'],
                    'claim_count': record['claim_count'],
                    'avg_amount': round(record['avg_amount'], 2),
                    'claim_ids': record['claim_ids'],
                    'fraud_type': 'Medical Mill',
                    'suspicion_score': min(100, record['claim_count'] * 5)
                })
            
            # Flag suspicious providers
            if mills:
                for mill in mills:
                    query_flag = """
                    MATCH (m:MedicalProvider {id: $provider_id})
                    SET m.suspicious = true,
                        m.suspicion_type = 'Medical Mill',
                        m.suspicion_score = $score
                    """
                    session.run(query_flag, 
                               provider_id=mill['provider_id'],
                               score=mill['suspicion_score'])
                
                print(f"   ✓ Found {len(mills)} suspicious medical providers")
                for mill in mills[:5]:
                    print(f"      - {mill['provider_name']}: {mill['claim_count']} claims, ${mill['avg_amount']} avg")
            else:
                print("   ✓ No medical mills detected")
            
            return mills
    
    def detect_bodyshop_kickbacks(self, min_shared_claims=3):
        """
        Detect body shop kickback schemes - attorneys consistently referring to same body shop
        """
        print("\n🔍 Detecting Body Shop Kickbacks...")
        
        with self.driver.session() as session:
            query = """
            MATCH (c:Claim)-[:REPRESENTED_BY]->(a:Attorney)
            MATCH (c)-[:REPAIRED_AT]->(b:BodyShop)
            WHERE c.is_fraud = false
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
                    'suspicion_score': min(100, record['shared_claims'] * 10)
                })
            
            # Flag suspicious relationships
            if kickbacks:
                for kb in kickbacks:
                    query_flag = """
                    MATCH (a:Attorney {id: $attorney_id})
                    MATCH (b:BodyShop {id: $bodyshop_id})
                    SET a.suspicious = true,
                        a.suspicion_type = 'Kickback Scheme',
                        a.suspicion_score = $score,
                        b.suspicious = true,
                        b.suspicion_type = 'Kickback Scheme',
                        b.suspicion_score = $score
                    MERGE (a)-[r:SUSPICIOUS_RELATIONSHIP]->(b)
                    SET r.shared_claims = $shared_claims
                    """
                    session.run(query_flag,
                               attorney_id=kb['attorney_id'],
                               bodyshop_id=kb['bodyshop_id'],
                               score=kb['suspicion_score'],
                               shared_claims=kb['shared_claims'])
                
                print(f"   ✓ Found {len(kickbacks)} suspicious attorney-bodyshop relationships")
                for kb in kickbacks[:5]:
                    print(f"      - {kb['attorney_name']} → {kb['bodyshop_name']}: {kb['shared_claims']} claims")
            else:
                print("   ✓ No kickback schemes detected")
            
            return kickbacks
    
    def detect_staged_accidents(self, min_shared_claims=2, min_participants=2):
        """
        Detect staged accidents - same people appearing in multiple claims together
        """
        print("\n🔍 Detecting Staged Accidents...")
        
        with self.driver.session() as session:
            query = """
            MATCH (c:Claim)-[:FILED_BY|WITNESSED_BY]->(p:Person)
            WHERE c.is_fraud = false AND c.claim_type = 'Auto'
            WITH p, collect(DISTINCT c) as claims
            WHERE size(claims) >= $min_shared_claims
            UNWIND claims as claim1
            UNWIND claims as claim2
            WITH p, claim1, claim2
            WHERE id(claim1) < id(claim2)
            
            MATCH (claim1)-[:FILED_BY|WITNESSED_BY]->(other:Person)
            MATCH (claim2)-[:FILED_BY|WITNESSED_BY]->(other)
            WHERE p.id <> other.id
            
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
            
            result = session.run(query, 
                               min_shared_claims=min_shared_claims,
                               min_participants=min_participants)
            
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
                        'claim_ids': record['claim_ids'],
                        'fraud_type': 'Staged Accident',
                        'suspicion_score': min(100, record['shared_claims'] * 20)
                    })
            
            # Flag suspicious people
            if staged:
                suspicious_people = set()
                for accident in staged:
                    suspicious_people.add(accident['person1_id'])
                    suspicious_people.add(accident['person2_id'])
                
                for person_id in suspicious_people:
                    query_flag = """
                    MATCH (p:Person {id: $person_id})
                    SET p.suspicious = true,
                        p.suspicion_type = 'Staged Accident',
                        p.suspicion_score = $score
                    """
                    session.run(query_flag, 
                               person_id=person_id,
                               score=50)
                
                print(f"   ✓ Found {len(staged)} suspicious person pairs in multiple claims")
                print(f"   ✓ Flagged {len(suspicious_people)} suspicious individuals")
                for acc in staged[:5]:
                    print(f"      - {acc['person1_id']} & {acc['person2_id']}: {acc['shared_claims']} shared claims")
            else:
                print("   ✓ No staged accidents detected")
            
            return staged
    
    def detect_phantom_passengers(self, min_connections=3):
        """
        Detect phantom passengers - people connected to many claimants but no direct claims
        """
        print("\n🔍 Detecting Phantom Passengers...")
        
        with self.driver.session() as session:
            query = """
            MATCH (p:Person:Claimant)-[:KNOWS]-(connected:Person:Claimant)
            WHERE p.is_fraud = false
            WITH connected, collect(DISTINCT p) as claimants, count(DISTINCT p) as connection_count
            WHERE connection_count >= $min_connections
            OPTIONAL MATCH (connected)-[:FILED_BY]-(c:Claim)
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
                    'suspicion_score': min(100, record['connection_count'] * 15)
                })
            
            # Flag suspicious phantom passengers
            if phantoms:
                for phantom in phantoms:
                    query_flag = """
                    MATCH (p:Person {id: $person_id})
                    SET p.suspicious = true,
                        p.suspicion_type = 'Phantom Passenger',
                        p.suspicion_score = $score
                    """
                    session.run(query_flag,
                               person_id=phantom['person_id'],
                               score=phantom['suspicion_score'])
                
                print(f"   ✓ Found {len(phantoms)} suspicious phantom passengers")
                for phantom in phantoms[:5]:
                    print(f"      - {phantom['person_name']}: {phantom['claim_count']} claims, {phantom['connection_count']} connections")
            else:
                print("   ✓ No phantom passengers detected")
            
            return phantoms
    
    def calculate_network_metrics(self):
        """
        Calculate network centrality metrics to identify key fraud nodes
        """
        print("\n📊 Calculating Network Metrics...")
        
        with self.driver.session() as session:
            # Degree centrality - find highly connected nodes
            query_degree = """
            MATCH (n)
            WHERE n.is_fraud = false
            WITH n, size((n)--()) as degree
            WHERE degree > 5
            SET n.degree_centrality = degree
            RETURN labels(n)[0] as node_type, count(n) as count, avg(degree) as avg_degree
            """
            
            result = session.run(query_degree)
            print("\n   High-degree nodes (potential fraud hubs):")
            for record in result:
                print(f"      - {record['node_type']}: {record['count']} nodes, avg degree {record['avg_degree']:.2f}")
            
            # Betweenness centrality - find bridge nodes
            query_betweenness = """
            MATCH (n)
            WHERE n.suspicious = true
            RETURN labels(n)[0] as node_type, 
                   n.suspicion_type as fraud_type,
                   count(n) as suspicious_count
            ORDER BY suspicious_count DESC
            """
            
            result = session.run(query_betweenness)
            print("\n   Suspicious nodes by type:")
            for record in result:
                print(f"      - {record['node_type']} ({record['fraud_type']}): {record['suspicious_count']}")
    
    def get_suspicious_communities(self):
        """
        Get all flagged suspicious communities for visualization
        """
        with self.driver.session() as session:
            query = """
            MATCH (n)
            WHERE n.suspicious = true
            RETURN n.id as id,
                   labels(n) as labels,
                   n.name as name,
                   n.suspicion_type as fraud_type,
                   n.suspicion_score as score
            ORDER BY n.suspicion_score DESC
            """
            
            result = session.run(query)
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
    
    def run_all_detections(self):
        """
        Run all fraud detection algorithms
        """
        print("=" * 60)
        print("FRAUD DETECTION ANALYSIS")
        print("=" * 60)
        
        results = {}
        
        # Run each detection algorithm
        results['medical_mills'] = self.detect_medical_mills(min_claims=5)
        results['kickbacks'] = self.detect_bodyshop_kickbacks(min_shared_claims=3)
        results['staged_accidents'] = self.detect_staged_accidents(min_shared_claims=2)
        results['phantom_passengers'] = self.detect_phantom_passengers(min_connections=3)
        
        # Calculate network metrics
        self.calculate_network_metrics()
        
        # Get summary
        communities = self.get_suspicious_communities()
        
        print("\n" + "=" * 60)
        print("DETECTION SUMMARY")
        print("=" * 60)
        print(f"Total suspicious entities flagged: {len(communities)}")
        print(f"  Medical Mills: {len(results['medical_mills'])}")
        print(f"  Kickback Schemes: {len(results['kickbacks'])}")
        print(f"  Staged Accidents: {len(results['staged_accidents'])}")
        print(f"  Phantom Passengers: {len(results['phantom_passengers'])}")
        
        return results

if __name__ == "__main__":
    # Configuration
    NEO4J_URI = "neo4j+s://your-instance.databases.neo4j.io"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "your-password"
    
    # Run fraud detection
    detector = FraudDetector(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    results = detector.run_all_detections()
    detector.close()
    
    print("\n✅ Fraud detection complete!")
    print("   Run the Streamlit app to visualize suspicious communities")
    print("   Command: streamlit run app.py")