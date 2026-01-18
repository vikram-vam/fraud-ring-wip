"""
Synthetic Data Generator for Insurance Fraud Detection
Generates realistic insurance data with explicit and implicit fraud patterns

Generation Philosophy:
- Explicit Fraud: Labeled patterns (is_fraud=true) for training/demo - clearly visible
- Implicit Fraud: Unlabeled patterns for detection algorithms to find
- Near-Miss Legitimate: Borderline legitimate patterns to test false positive resistance

Implicit Fraud Tiers (aligned with detection thresholds):
- Tier 1 (Borderline): Just at/below default detection thresholds - 40% of patterns
- Tier 2 (Moderate): Clearly above thresholds but not extreme - 40% of patterns  
- Tier 3 (Obvious): High-confidence fraud patterns - 20% of patterns

This tiered approach enables meaningful parameter exploration in the UI.
"""

import random
from datetime import datetime, timedelta
from neo4j import GraphDatabase
import streamlit as st


class FraudDataGenerator:
    def __init__(self):
        """Initialize generator with Neo4j connection from Streamlit secrets."""
        try:
            neo4j_uri = st.secrets["neo4j"]["uri"]
            neo4j_user = st.secrets["neo4j"]["user"]
            neo4j_password = st.secrets["neo4j"]["password"]
        except Exception as e:
            raise ConnectionError(f"Failed to load Neo4j secrets: {e}")

        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        # Global counters for UNIQUE IDs
        self.claim_counter = 0
        self.person_counter = 0
        self.provider_counter = 0
        self.attorney_counter = 0
        self.bodyshop_counter = 0
        self.adjuster_counter = 0
        
        # Pre-create pools of adjusters (shared across claims)
        self.adjuster_pool = []
        
        # Pre-create pools of service providers (reused realistically)
        self.medical_provider_pool = []
        self.attorney_pool = []
        self.bodyshop_pool = []
        
        # Track generated patterns for reporting
        self.generation_stats = {
            'legitimate_claims': 0,
            'explicit_fraud': {
                'medical_mill': 0,
                'kickback': 0,
                'staged': 0,
                'phantom': 0,
                'adjuster_collusion': 0
            },
            'implicit_fraud': {
                'tier1': {'medical_mill': 0, 'kickback': 0, 'staged': 0, 'phantom': 0, 'adjuster_collusion': 0},
                'tier2': {'medical_mill': 0, 'kickback': 0, 'staged': 0, 'phantom': 0, 'adjuster_collusion': 0},
                'tier3': {'medical_mill': 0, 'kickback': 0, 'staged': 0, 'phantom': 0, 'adjuster_collusion': 0}
            },
            'near_miss_legitimate': {
                'high_volume_providers': 0,
                'repeat_referrals': 0,
                'repeat_witnesses': 0
            }
        }

    def close(self):
        self.driver.close()

    def clear_database(self):
        """Clear all existing data"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")

    def create_indexes(self):
        """Create indexes for better performance"""
        with self.driver.session() as session:
            indexes = [
                "CREATE INDEX claim_id IF NOT EXISTS FOR (c:Claim) ON (c.id)",
                "CREATE INDEX person_id IF NOT EXISTS FOR (p:Person) ON (p.id)",
                "CREATE INDEX provider_id IF NOT EXISTS FOR (m:MedicalProvider) ON (m.id)",
                "CREATE INDEX attorney_id IF NOT EXISTS FOR (a:Attorney) ON (a.id)",
                "CREATE INDEX bodyshop_id IF NOT EXISTS FOR (b:BodyShop) ON (b.id)"
            ]
            for idx in indexes:
                try:
                    session.run(idx)
                except Exception:
                    pass
            print("✓ Indexes created")
    
    def create_adjuster_pool(self, num_adjusters=20):
        """Create a pool of adjusters to be reused across claims"""
        print(f"\nCreating pool of {num_adjusters} adjusters...")
        
        with self.driver.session() as session:
            for i in range(num_adjusters):
                adjuster_id = f"ADJ_{self.adjuster_counter:05d}"
                adjuster_name = self.generate_name()
                
                query = """
                CREATE (a:Person:Adjuster {
                    id: $adjuster_id,
                    name: $adjuster_name,
                    employee_id: $employee_id
                })
                """
                
                session.run(query,
                           adjuster_id=adjuster_id,
                           adjuster_name=adjuster_name,
                           employee_id=f"EMP-{self.adjuster_counter:05d}")
                
                self.adjuster_pool.append(adjuster_id)
                self.adjuster_counter += 1
        
        print(f"✓ Created {num_adjusters} adjusters")
    
    def create_service_provider_pools(self):
        """Create pools of service providers (realistic reuse)"""
        print("\nCreating service provider pools...")
        
        with self.driver.session() as session:
            # Create 15-25 medical providers
            num_providers = random.randint(15, 25)
            for i in range(num_providers):
                provider_id = f"MED_{self.provider_counter:05d}"
                provider_name = f"{self.generate_name().split()[1]} Medical Center"
                
                query = """
                CREATE (m:MedicalProvider {
                    id: $provider_id,
                    name: $provider_name,
                    license: $license
                })
                """
                
                session.run(query,
                           provider_id=provider_id,
                           provider_name=provider_name,
                           license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                self.medical_provider_pool.append(provider_id)
                self.provider_counter += 1
            
            # Create 10-15 attorneys
            num_attorneys = random.randint(10, 15)
            for i in range(num_attorneys):
                attorney_id = f"ATT_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                
                query = """
                CREATE (a:Attorney {
                    id: $attorney_id,
                    name: $attorney_name,
                    bar_number: $bar_number
                })
                """
                
                session.run(query,
                           attorney_id=attorney_id,
                           attorney_name=attorney_name,
                           bar_number=f"BAR-{random.randint(100000, 999999)}")
                
                self.attorney_pool.append(attorney_id)
                self.attorney_counter += 1
            
            # Create 8-12 body shops
            num_bodyshops = random.randint(8, 12)
            for i in range(num_bodyshops):
                bodyshop_id = f"BS_{self.bodyshop_counter:05d}"
                bodyshop_name = f"{self.generate_name().split()[1]} Auto Body Shop"
                
                query = """
                CREATE (b:BodyShop {
                    id: $bodyshop_id,
                    name: $bodyshop_name,
                    license: $license
                })
                """
                
                session.run(query,
                           bodyshop_id=bodyshop_id,
                           bodyshop_name=bodyshop_name,
                           license=f"BS-LIC-{random.randint(10000, 99999)}")
                
                self.bodyshop_pool.append(bodyshop_id)
                self.bodyshop_counter += 1
        
        print(f"✓ Created {len(self.medical_provider_pool)} medical providers")
        print(f"✓ Created {len(self.attorney_pool)} attorneys")
        print(f"✓ Created {len(self.bodyshop_pool)} body shops")

    def generate_name(self):
        """Generate random person name"""
        first_names = ["John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa",
                       "William", "Maria", "James", "Jennifer", "Richard", "Linda", "Thomas",
                       "Christopher", "Patricia", "Daniel", "Barbara", "Matthew", "Nancy",
                       "Charles", "Susan", "Joseph", "Jessica", "Mark", "Karen", "Donald", "Betty",
                       "Steven", "Margaret", "Andrew", "Sandra", "Joshua", "Ashley", "Kevin", "Dorothy"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
                      "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
                      "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
                      "Thompson", "White", "Harris", "Clark", "Lewis", "Robinson", "Walker",
                      "Young", "Allen", "King", "Wright", "Scott", "Green", "Baker", "Adams"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"

    def generate_date(self, start_days_ago=365, end_days_ago=0):
        """Generate random date"""
        start = datetime.now() - timedelta(days=start_days_ago)
        end = datetime.now() - timedelta(days=end_days_ago)
        delta = end - start
        random_days = random.randint(0, max(1, delta.days))
        return (start + timedelta(days=random_days)).isoformat()

    def create_legitimate_claims(self, num_claims=100):
        """Create legitimate insurance claims with realistic relationships"""
        print(f"\nGenerating {num_claims} legitimate claims...")
        
        # Verify pools are populated
        if not self.adjuster_pool:
            raise ValueError("Adjuster pool is empty! Call create_adjuster_pool() first.")
        if not self.medical_provider_pool:
            raise ValueError("Medical provider pool is empty! Call create_service_provider_pools() first.")

        with self.driver.session() as session:
            for i in range(num_claims):
                claim_id = f"CLM_{self.claim_counter:05d}"
                claim_type = random.choice(["Auto", "Property", "Medical"])
                self.claim_counter += 1

                # Create unique claimant
                claimant_id = f"P_{self.person_counter:05d}"
                claimant_name = self.generate_name()
                self.person_counter += 1
                
                # Select adjuster from pool
                adjuster_id = random.choice(self.adjuster_pool)
                
                # Base query - every claim has claimant and adjuster
                query = """
                MATCH (adjuster:Person:Adjuster {id: $adjuster_id})
                CREATE (c:Claim {
                    id: $claim_id,
                    name: $claim_name,
                    claim_amount: $amount,
                    claim_date: $claim_date,
                    claim_type: $claim_type,
                    is_fraud: false
                })
                CREATE (claimant:Person:Claimant {
                    id: $claimant_id,
                    name: $claimant_name,
                    ssn: $claimant_ssn,
                    phone: $claimant_phone
                })
                CREATE (c)-[:FILED_BY]->(claimant)
                CREATE (c)-[:HANDLED_BY]->(adjuster)
                """
                
                params = {
                    "claim_id": claim_id,
                    "claim_name": f"Legitimate {claim_type} Claim {i+1}",
                    "amount": round(random.uniform(1000, 50000), 2),
                    "claim_date": self.generate_date(),
                    "claim_type": claim_type,
                    "claimant_id": claimant_id,
                    "claimant_name": claimant_name,
                    "claimant_ssn": f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    "claimant_phone": f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                    "adjuster_id": adjuster_id
                }
                
                session.run(query, **params)
                
                # Add witnesses (70% of claims)
                if random.random() < 0.7:
                    self.add_witness(session, claim_id)
                
                # Add service providers based on claim type
                if claim_type == "Medical":
                    self.add_medical_provider(session, claim_id)
                    if random.random() < 0.3:
                        self.add_attorney(session, claim_id)
                
                elif claim_type == "Auto":
                    if random.random() < 0.8:
                        self.add_bodyshop(session, claim_id)
                    if random.random() < 0.4:
                        self.add_attorney(session, claim_id)
                
                elif claim_type == "Property":
                    if random.random() < 0.2:
                        self.add_attorney(session, claim_id)
        
        self.generation_stats['legitimate_claims'] = num_claims
        print(f"✓ Created {num_claims} legitimate claims with realistic relationships")

    def add_witness(self, session, claim_id):
        """Add unique witness to a claim"""
        witness_id = f"P_{self.person_counter:05d}"
        witness_name = self.generate_name()
        self.person_counter += 1
        
        query = """
        MATCH (c:Claim {id: $claim_id})
        CREATE (w:Person:Witness {
            id: $witness_id,
            name: $witness_name,
            phone: $witness_phone
        })
        CREATE (c)-[:WITNESSED_BY]->(w)
        """
        
        session.run(query,
                   claim_id=claim_id,
                   witness_id=witness_id,
                   witness_name=witness_name,
                   witness_phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
    
    def add_medical_provider(self, session, claim_id):
        """Link claim to medical provider from pool"""
        provider_id = random.choice(self.medical_provider_pool)
        
        query = """
        MATCH (c:Claim {id: $claim_id})
        MATCH (m:MedicalProvider {id: $provider_id})
        CREATE (c)-[:TREATED_AT]->(m)
        """
        
        session.run(query, claim_id=claim_id, provider_id=provider_id)
    
    def add_attorney(self, session, claim_id):
        """Link claim to attorney from pool"""
        attorney_id = random.choice(self.attorney_pool)
        
        query = """
        MATCH (c:Claim {id: $claim_id})
        MATCH (a:Attorney {id: $attorney_id})
        CREATE (c)-[:REPRESENTED_BY]->(a)
        """
        
        session.run(query, claim_id=claim_id, attorney_id=attorney_id)
    
    def add_bodyshop(self, session, claim_id):
        """Link claim to body shop from pool"""
        bodyshop_id = random.choice(self.bodyshop_pool)
        
        query = """
        MATCH (c:Claim {id: $claim_id})
        MATCH (b:BodyShop {id: $bodyshop_id})
        CREATE (c)-[:REPAIRED_AT]->(b)
        """
        
        session.run(query, claim_id=claim_id, bodyshop_id=bodyshop_id)

    # =========================================================================
    # EXPLICIT FRAUD PATTERNS (Labeled - is_fraud=true)
    # =========================================================================

    def create_medical_mill(self, num_rings=3):
        """Create Medical Mill fraud pattern (LABELED)"""
        print(f"\nGenerating {num_rings} Medical Mill fraud rings (labeled)...")

        with self.driver.session() as session:
            for ring in range(num_rings):
                provider_id = f"MED_FRAUD_MM_{ring:05d}_{self.provider_counter:05d}"
                self.provider_counter += 1

                query_provider = """
                CREATE (m:MedicalProvider {
                    id: $provider_id,
                    name: $provider_name,
                    license: $license,
                    is_fraud: true,
                    fraud_type: 'Medical Mill'
                })
                """

                session.run(query_provider,
                            provider_id=provider_id,
                            provider_name=f"Fraudulent Medical Center {ring}",
                            license=f"FRAUD-MED-{random.randint(10000, 99999)}")

                attorney_id = f"ATT_FRAUD_MM_{ring:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                query_attorney = """
                CREATE (a:Attorney {
                    id: $attorney_id,
                    name: $attorney_name,
                    bar_number: $bar_number,
                    is_fraud: true,
                    fraud_type: 'Medical Mill'
                })
                """
                
                session.run(query_attorney,
                           attorney_id=attorney_id,
                           attorney_name=attorney_name,
                           bar_number=f"BAR-FRAUD-{random.randint(100000, 999999)}")

                num_claims_in_ring = random.randint(8, 15)

                for i in range(num_claims_in_ring):
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    claimant_id = f"P_{self.person_counter:05d}"
                    claimant_name = self.generate_name()
                    self.person_counter += 1
                    
                    adjuster_id = random.choice(self.adjuster_pool)

                    query_claim = """
                    MATCH (m:MedicalProvider {id: $provider_id})
                    MATCH (a:Attorney {id: $attorney_id})
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $amount,
                        claim_date: $claim_date,
                        claim_type: 'Medical',
                        is_fraud: true,
                        fraud_type: 'Medical Mill'
                    })
                    CREATE (claimant:Person:Claimant {
                        id: $claimant_id,
                        name: $claimant_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    CREATE (c)-[:FILED_BY]->(claimant)
                    CREATE (c)-[:TREATED_AT]->(m)
                    CREATE (c)-[:REPRESENTED_BY]->(a)
                    CREATE (c)-[:HANDLED_BY]->(adj)
                    """

                    session.run(query_claim,
                                provider_id=provider_id,
                                attorney_id=attorney_id,
                                adjuster_id=adjuster_id,
                                claim_id=claim_id,
                                claim_name=f"Medical Mill Claim {ring}-{i}",
                                amount=round(random.uniform(15000, 45000), 2),
                                claim_date=self.generate_date(90, 0),
                                claimant_id=claimant_id,
                                claimant_name=claimant_name,
                                ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                                phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

        self.generation_stats['explicit_fraud']['medical_mill'] = num_rings
        print(f"✓ Created {num_rings} Medical Mill fraud rings (labeled)")

    def create_bodyshop_kickback(self, num_rings=3):
        """Create Body Shop Kickback pattern (LABELED)"""
        print(f"\nGenerating {num_rings} Body Shop Kickback fraud rings (labeled)...")

        with self.driver.session() as session:
            for ring in range(num_rings):
                attorney_id = f"ATT_FRAUD_BK_{ring:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                bodyshop_id = f"BS_FRAUD_BK_{ring:05d}_{self.bodyshop_counter:05d}"
                bodyshop_name = f"Kickback Body Shop {ring}"
                self.bodyshop_counter += 1

                query_setup = """
                CREATE (a:Attorney {
                    id: $attorney_id,
                    name: $attorney_name,
                    bar_number: $bar_number,
                    is_fraud: true,
                    fraud_type: 'Body Shop Kickback'
                })
                CREATE (b:BodyShop {
                    id: $bodyshop_id,
                    name: $bodyshop_name,
                    license: $license,
                    is_fraud: true,
                    fraud_type: 'Body Shop Kickback'
                })
                CREATE (a)-[:REFERS_TO {kickback_amount: $kickback}]->(b)
                """

                session.run(query_setup,
                            attorney_id=attorney_id,
                            attorney_name=attorney_name,
                            bar_number=f"BAR-FRAUD-{random.randint(100000, 999999)}",
                            bodyshop_id=bodyshop_id,
                            bodyshop_name=bodyshop_name,
                            license=f"BS-FRAUD-{random.randint(10000, 99999)}",
                            kickback=round(random.uniform(500, 2000), 2))

                num_claims_in_ring = random.randint(6, 12)

                for i in range(num_claims_in_ring):
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    claimant_id = f"P_{self.person_counter:05d}"
                    claimant_name = self.generate_name()
                    self.person_counter += 1
                    
                    adjuster_id = random.choice(self.adjuster_pool)

                    query_claim = """
                    MATCH (a:Attorney {id: $attorney_id})
                    MATCH (b:BodyShop {id: $bodyshop_id})
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $amount,
                        claim_date: $claim_date,
                        claim_type: 'Auto',
                        is_fraud: true,
                        fraud_type: 'Body Shop Kickback'
                    })
                    CREATE (claimant:Person:Claimant {
                        id: $claimant_id,
                        name: $claimant_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    CREATE (c)-[:FILED_BY]->(claimant)
                    CREATE (c)-[:REPRESENTED_BY]->(a)
                    CREATE (c)-[:REPAIRED_AT]->(b)
                    CREATE (c)-[:HANDLED_BY]->(adj)
                    """

                    session.run(query_claim,
                                attorney_id=attorney_id,
                                bodyshop_id=bodyshop_id,
                                adjuster_id=adjuster_id,
                                claim_id=claim_id,
                                claim_name=f"Kickback Claim {ring}-{i}",
                                amount=round(random.uniform(8000, 25000), 2),
                                claim_date=self.generate_date(120, 0),
                                claimant_id=claimant_id,
                                claimant_name=claimant_name,
                                ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                                phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

        self.generation_stats['explicit_fraud']['kickback'] = num_rings
        print(f"✓ Created {num_rings} Body Shop Kickback fraud rings (labeled)")

    def create_staged_accident(self, num_rings=2):
        """Create Staged Accident pattern (LABELED)"""
        print(f"\nGenerating {num_rings} Staged Accident fraud rings (labeled)...")

        with self.driver.session() as session:
            for ring in range(num_rings):
                num_conspirators = random.randint(4, 7)
                conspirator_ids = []

                for i in range(num_conspirators):
                    conspirator_id = f"P_{self.person_counter:05d}"
                    conspirator_name = self.generate_name()
                    self.person_counter += 1
                    
                    conspirator_ids.append(conspirator_id)

                    query_person = """
                    CREATE (p:Person:Claimant {
                        id: $person_id,
                        name: $person_name,
                        ssn: $ssn,
                        phone: $phone,
                        is_fraud: true,
                        fraud_type: 'Staged Accident'
                    })
                    """

                    session.run(query_person,
                                person_id=conspirator_id,
                                person_name=conspirator_name,
                                ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                                phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

                num_accidents = random.randint(3, 6)

                for acc in range(num_accidents):
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    adjuster_id = random.choice(self.adjuster_pool)

                    participants = random.sample(conspirator_ids, random.randint(2, min(4, len(conspirator_ids))))

                    query_claim = """
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $amount,
                        claim_date: $claim_date,
                        claim_type: 'Auto',
                        is_fraud: true,
                        fraud_type: 'Staged Accident'
                    })
                    CREATE (c)-[:HANDLED_BY]->(adj)
                    """

                    session.run(query_claim,
                                adjuster_id=adjuster_id,
                                claim_id=claim_id,
                                claim_name=f"Staged Accident {ring}-{acc}",
                                amount=round(random.uniform(10000, 40000), 2),
                                claim_date=self.generate_date(180, 30))

                    for idx, person_id in enumerate(participants):
                        role = "FILED_BY" if idx == 0 else "WITNESSED_BY"

                        query_link = f"""
                        MATCH (c:Claim {{id: $claim_id}})
                        MATCH (p:Person {{id: $person_id}})
                        CREATE (c)-[:{role}]->(p)
                        """

                        session.run(query_link, claim_id=claim_id, person_id=person_id)

        self.generation_stats['explicit_fraud']['staged'] = num_rings
        print(f"✓ Created {num_rings} Staged Accident fraud rings (labeled)")

    def create_phantom_passenger(self, num_rings=3):
        """Create Phantom Passenger pattern (LABELED)"""
        print(f"\nGenerating {num_rings} Phantom Passenger fraud rings (labeled)...")

        with self.driver.session() as session:
            for ring in range(num_rings):
                main_claimant_id = f"P_{self.person_counter:05d}"
                main_claimant_name = self.generate_name()
                self.person_counter += 1

                query_claimant = """
                CREATE (p:Person:Claimant {
                    id: $claimant_id,
                    name: $claimant_name,
                    ssn: $ssn,
                    phone: $phone,
                    is_fraud: true,
                    fraud_type: 'Phantom Passenger'
                })
                """

                session.run(query_claimant,
                            claimant_id=main_claimant_id,
                            claimant_name=main_claimant_name,
                            ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                            phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

                num_phantoms = random.randint(3, 6)

                for i in range(num_phantoms):
                    phantom_id = f"P_{self.person_counter:05d}"
                    phantom_name = self.generate_name()
                    self.person_counter += 1
                    
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    adjuster_id = random.choice(self.adjuster_pool)

                    query = """
                    MATCH (claimant:Person {id: $claimant_id})
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    CREATE (phantom:Person:Claimant {
                        id: $phantom_id,
                        name: $phantom_name,
                        ssn: $ssn,
                        phone: $phone,
                        is_fraud: true,
                        fraud_type: 'Phantom Passenger'
                    })
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $amount,
                        claim_date: $claim_date,
                        claim_type: 'Auto',
                        is_fraud: true,
                        fraud_type: 'Phantom Passenger'
                    })
                    CREATE (c)-[:FILED_BY]->(phantom)
                    CREATE (c)-[:HANDLED_BY]->(adj)
                    CREATE (phantom)-[:KNOWS]->(claimant)
                    """

                    session.run(query,
                                claimant_id=main_claimant_id,
                                phantom_id=phantom_id,
                                phantom_name=phantom_name,
                                adjuster_id=adjuster_id,
                                ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                                phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                                claim_id=claim_id,
                                claim_name=f"Phantom Passenger Claim {ring}-{i}",
                                amount=round(random.uniform(8000, 30000), 2),
                                claim_date=self.generate_date(150, 20))

        self.generation_stats['explicit_fraud']['phantom'] = num_rings
        print(f"✓ Created {num_rings} Phantom Passenger fraud rings (labeled)")

    def create_adjuster_collusion(self, num_rings=2):
        """Create Adjuster-Provider Collusion fraud pattern (LABELED)"""
        print(f"\nGenerating {num_rings} Adjuster-Provider Collusion fraud rings (labeled)...")

        with self.driver.session() as session:
            for ring in range(num_rings):
                # Create corrupt adjuster
                adjuster_id = f"ADJ_FRAUD_AC_{ring:05d}_{self.adjuster_counter:05d}"
                adjuster_name = self.generate_name()
                self.adjuster_counter += 1
                
                # Create colluding medical provider
                provider_id = f"MED_FRAUD_AC_{ring:05d}_{self.provider_counter:05d}"
                provider_name = f"Collusion Medical Center {ring}"
                self.provider_counter += 1

                query_setup = """
                CREATE (adj:Person:Adjuster {
                    id: $adjuster_id,
                    name: $adjuster_name,
                    employee_id: $employee_id,
                    is_fraud: true,
                    fraud_type: 'Adjuster-Provider Collusion'
                })
                CREATE (m:MedicalProvider {
                    id: $provider_id,
                    name: $provider_name,
                    license: $license,
                    is_fraud: true,
                    fraud_type: 'Adjuster-Provider Collusion'
                })
                CREATE (adj)-[:COLLUDES_WITH {kickback_pct: $kickback}]->(m)
                """

                session.run(query_setup,
                            adjuster_id=adjuster_id,
                            adjuster_name=adjuster_name,
                            employee_id=f"EMP-FRAUD-{random.randint(10000, 99999)}",
                            provider_id=provider_id,
                            provider_name=provider_name,
                            license=f"MED-FRAUD-{random.randint(10000, 99999)}",
                            kickback=round(random.uniform(5, 15), 1))

                # Create 6-10 claims handled by this adjuster at this provider
                num_claims_in_ring = random.randint(6, 10)

                for i in range(num_claims_in_ring):
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    claimant_id = f"P_{self.person_counter:05d}"
                    claimant_name = self.generate_name()
                    self.person_counter += 1

                    query_claim = """
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    MATCH (m:MedicalProvider {id: $provider_id})
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $amount,
                        claim_date: $claim_date,
                        claim_type: 'Medical',
                        is_fraud: true,
                        fraud_type: 'Adjuster-Provider Collusion'
                    })
                    CREATE (claimant:Person:Claimant {
                        id: $claimant_id,
                        name: $claimant_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    CREATE (c)-[:FILED_BY]->(claimant)
                    CREATE (c)-[:TREATED_AT]->(m)
                    CREATE (c)-[:HANDLED_BY]->(adj)
                    """

                    session.run(query_claim,
                                adjuster_id=adjuster_id,
                                provider_id=provider_id,
                                claim_id=claim_id,
                                claim_name=f"Adjuster Collusion Claim {ring}-{i}",
                                amount=round(random.uniform(12000, 40000), 2),
                                claim_date=self.generate_date(100, 0),
                                claimant_id=claimant_id,
                                claimant_name=claimant_name,
                                ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                                phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

        self.generation_stats['explicit_fraud']['adjuster_collusion'] = num_rings
        print(f"✓ Created {num_rings} Adjuster-Provider Collusion fraud rings (labeled)")

    # =========================================================================
    # TIERED IMPLICIT FRAUD PATTERNS (Unlabeled - for detection)
    # =========================================================================
    
    def create_tiered_implicit_fraud_patterns(self, tier_config=None):
        """
        Create TIERED unlabeled fraud patterns for detection algorithm testing.
        
        Tiers align with detection thresholds:
        - Tier 1 (Borderline): At or just below default thresholds - harder to detect
        - Tier 2 (Moderate): Clearly above thresholds - detectable at defaults
        - Tier 3 (Obvious): High values - clearly fraudulent patterns
        
        Distribution philosophy: 40% Tier 1, 40% Tier 2, 20% Tier 3
        This creates a realistic pyramid where obvious fraud is rare.
        
        Args:
            tier_config: Dict with tier counts for each fraud type
        """
        if tier_config is None:
            # Default: balanced distribution
            tier_config = {
                'medical_mill': {'tier1': 2, 'tier2': 2, 'tier3': 1},
                'kickback': {'tier1': 2, 'tier2': 1, 'tier3': 1},
                'staged': {'tier1': 2, 'tier2': 1, 'tier3': 1},
                'phantom': {'tier1': 2, 'tier2': 1, 'tier3': 1},
                'adjuster_collusion': {'tier1': 2, 'tier2': 1, 'tier3': 1}
            }
        
        total = sum(
            sum(tiers.values()) 
            for tiers in tier_config.values()
        )
        print(f"\n{'='*60}")
        print(f"Generating {total} TIERED implicit fraud patterns (unlabeled)")
        print(f"{'='*60}")
        print("Tier 1 (Borderline): At/below default detection thresholds")
        print("Tier 2 (Moderate): Above thresholds, clearly suspicious")
        print("Tier 3 (Obvious): High-confidence fraud patterns")
        
        # Medical Mill tiers
        # Detection threshold: min_claims=5, min_avg_amount=15000
        mm_config = tier_config.get('medical_mill', {})
        self._create_implicit_medical_mill_tier1(mm_config.get('tier1', 0))  # 3-4 claims
        self._create_implicit_medical_mill_tier2(mm_config.get('tier2', 0))  # 5-7 claims
        self._create_implicit_medical_mill_tier3(mm_config.get('tier3', 0))  # 8-12 claims
        
        # Kickback tiers
        # Detection threshold: min_shared_claims=3
        kb_config = tier_config.get('kickback', {})
        self._create_implicit_kickback_tier1(kb_config.get('tier1', 0))  # 2 shared claims
        self._create_implicit_kickback_tier2(kb_config.get('tier2', 0))  # 3-4 shared claims
        self._create_implicit_kickback_tier3(kb_config.get('tier3', 0))  # 5-8 shared claims
        
        # Staged Accident tiers
        # Detection threshold: min_shared_claims=2
        sa_config = tier_config.get('staged', {})
        self._create_implicit_staged_tier1(sa_config.get('tier1', 0))  # 2 shared claims (borderline)
        self._create_implicit_staged_tier2(sa_config.get('tier2', 0))  # 3-4 shared claims
        self._create_implicit_staged_tier3(sa_config.get('tier3', 0))  # 5+ shared claims
        
        # Phantom Passenger tiers
        # Detection threshold: min_connections=3
        pp_config = tier_config.get('phantom', {})
        self._create_implicit_phantom_tier1(pp_config.get('tier1', 0))
        self._create_implicit_phantom_tier2(pp_config.get('tier2', 0))
        self._create_implicit_phantom_tier3(pp_config.get('tier3', 0))
        
        # Adjuster Collusion tiers
        # Detection threshold: min_adjuster_collusion=4
        ac_config = tier_config.get('adjuster_collusion', {})
        self._create_implicit_adjuster_collusion_tier1(ac_config.get('tier1', 0))
        self._create_implicit_adjuster_collusion_tier2(ac_config.get('tier2', 0))
        self._create_implicit_adjuster_collusion_tier3(ac_config.get('tier3', 0))
        
        self._print_implicit_fraud_summary()
    
    def _create_implicit_medical_mill_tier1(self, count):
        """Tier 1 Medical Mill: 3-4 claims, avg amount $12k-18k (borderline)"""
        if count == 0:
            return
        
        print(f"\n   Creating {count} Tier 1 Medical Mills (borderline: 3-4 claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                provider_id = f"MED_IMP_T1_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Community Health Clinic {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 3-4 claims (at or below default threshold of 5)
                num_claims = random.randint(3, 4)
                for j in range(num_claims):
                    self._create_implicit_medical_claim(session, provider_id, 
                                                        amount_range=(12000, 18000))
        
        self.generation_stats['implicit_fraud']['tier1']['medical_mill'] = count
    
    def _create_implicit_medical_mill_tier2(self, count):
        """Tier 2 Medical Mill: 5-7 claims, avg amount $18k-28k (moderate)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 2 Medical Mills (moderate: 5-7 claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                provider_id = f"MED_IMP_T2_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Regional Medical Group {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 5-7 claims (at/above default threshold)
                num_claims = random.randint(5, 7)
                for j in range(num_claims):
                    self._create_implicit_medical_claim(session, provider_id,
                                                        amount_range=(18000, 28000))
        
        self.generation_stats['implicit_fraud']['tier2']['medical_mill'] = count
    
    def _create_implicit_medical_mill_tier3(self, count):
        """Tier 3 Medical Mill: 8-12 claims, avg amount $28k-45k (obvious)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 3 Medical Mills (obvious: 8-12 claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                provider_id = f"MED_IMP_T3_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Specialty Treatment Center {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 8-12 claims (well above threshold)
                num_claims = random.randint(8, 12)
                for j in range(num_claims):
                    self._create_implicit_medical_claim(session, provider_id,
                                                        amount_range=(28000, 45000))
        
        self.generation_stats['implicit_fraud']['tier3']['medical_mill'] = count
    
    def _create_implicit_medical_claim(self, session, provider_id, amount_range):
        """Helper to create a medical claim linked to a provider"""
        claim_id = f"CLM_{self.claim_counter:05d}"
        self.claim_counter += 1
        
        claimant_id = f"P_{self.person_counter:05d}"
        claimant_name = self.generate_name()
        self.person_counter += 1
        
        adjuster_id = random.choice(self.adjuster_pool)
        
        session.run("""
            MATCH (m:MedicalProvider {id: $provider_id})
            MATCH (adj:Person:Adjuster {id: $adjuster_id})
            CREATE (c:Claim {
                id: $claim_id,
                name: $claim_name,
                claim_amount: $amount,
                claim_date: $claim_date,
                claim_type: 'Medical',
                is_fraud: false
            })
            CREATE (claimant:Person:Claimant {
                id: $claimant_id,
                name: $claimant_name,
                ssn: $ssn,
                phone: $phone
            })
            CREATE (c)-[:FILED_BY]->(claimant)
            CREATE (c)-[:TREATED_AT]->(m)
            CREATE (c)-[:HANDLED_BY]->(adj)
            """,
            provider_id=provider_id,
            adjuster_id=adjuster_id,
            claim_id=claim_id,
            claim_name=f"Medical Claim {claim_id}",
            amount=round(random.uniform(*amount_range), 2),
            claim_date=self.generate_date(90, 0),
            claimant_id=claimant_id,
            claimant_name=claimant_name,
            ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
    
    def _create_implicit_kickback_tier1(self, count):
        """Tier 1 Kickback: 2 shared claims (below default threshold of 3)"""
        if count == 0:
            return
        
        print(f"\n   Creating {count} Tier 1 Kickbacks (borderline: 2 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                attorney_id = f"ATT_IMP_T1_{i:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                bodyshop_id = f"BS_IMP_T1_{i:05d}_{self.bodyshop_counter:05d}"
                bodyshop_name = f"Quick Fix Auto {i}"
                self.bodyshop_counter += 1
                
                session.run("""
                    CREATE (a:Attorney {
                        id: $attorney_id,
                        name: $attorney_name,
                        bar_number: $bar_number
                    })
                    CREATE (b:BodyShop {
                        id: $bodyshop_id,
                        name: $bodyshop_name,
                        license: $license
                    })
                    """,
                    attorney_id=attorney_id,
                    attorney_name=attorney_name,
                    bar_number=f"BAR-{random.randint(100000, 999999)}",
                    bodyshop_id=bodyshop_id,
                    bodyshop_name=bodyshop_name,
                    license=f"BS-LIC-{random.randint(10000, 99999)}")
                
                # 2 shared claims (below threshold)
                for j in range(2):
                    self._create_implicit_kickback_claim(session, attorney_id, bodyshop_id)
        
        self.generation_stats['implicit_fraud']['tier1']['kickback'] = count
    
    def _create_implicit_kickback_tier2(self, count):
        """Tier 2 Kickback: 3-4 shared claims (at/above threshold)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 2 Kickbacks (moderate: 3-4 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                attorney_id = f"ATT_IMP_T2_{i:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                bodyshop_id = f"BS_IMP_T2_{i:05d}_{self.bodyshop_counter:05d}"
                bodyshop_name = f"Premier Auto Body {i}"
                self.bodyshop_counter += 1
                
                session.run("""
                    CREATE (a:Attorney {
                        id: $attorney_id,
                        name: $attorney_name,
                        bar_number: $bar_number
                    })
                    CREATE (b:BodyShop {
                        id: $bodyshop_id,
                        name: $bodyshop_name,
                        license: $license
                    })
                    """,
                    attorney_id=attorney_id,
                    attorney_name=attorney_name,
                    bar_number=f"BAR-{random.randint(100000, 999999)}",
                    bodyshop_id=bodyshop_id,
                    bodyshop_name=bodyshop_name,
                    license=f"BS-LIC-{random.randint(10000, 99999)}")
                
                # 3-4 shared claims
                num_claims = random.randint(3, 4)
                for j in range(num_claims):
                    self._create_implicit_kickback_claim(session, attorney_id, bodyshop_id)
        
        self.generation_stats['implicit_fraud']['tier2']['kickback'] = count
    
    def _create_implicit_kickback_tier3(self, count):
        """Tier 3 Kickback: 5-8 shared claims (obvious)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 3 Kickbacks (obvious: 5-8 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                attorney_id = f"ATT_IMP_T3_{i:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                bodyshop_id = f"BS_IMP_T3_{i:05d}_{self.bodyshop_counter:05d}"
                bodyshop_name = f"Discount Collision Center {i}"
                self.bodyshop_counter += 1
                
                session.run("""
                    CREATE (a:Attorney {
                        id: $attorney_id,
                        name: $attorney_name,
                        bar_number: $bar_number
                    })
                    CREATE (b:BodyShop {
                        id: $bodyshop_id,
                        name: $bodyshop_name,
                        license: $license
                    })
                    """,
                    attorney_id=attorney_id,
                    attorney_name=attorney_name,
                    bar_number=f"BAR-{random.randint(100000, 999999)}",
                    bodyshop_id=bodyshop_id,
                    bodyshop_name=bodyshop_name,
                    license=f"BS-LIC-{random.randint(10000, 99999)}")
                
                # 5-8 shared claims
                num_claims = random.randint(5, 8)
                for j in range(num_claims):
                    self._create_implicit_kickback_claim(session, attorney_id, bodyshop_id)
        
        self.generation_stats['implicit_fraud']['tier3']['kickback'] = count
    
    def _create_implicit_kickback_claim(self, session, attorney_id, bodyshop_id):
        """Helper to create a kickback-style claim"""
        claim_id = f"CLM_{self.claim_counter:05d}"
        self.claim_counter += 1
        
        claimant_id = f"P_{self.person_counter:05d}"
        claimant_name = self.generate_name()
        self.person_counter += 1
        
        adjuster_id = random.choice(self.adjuster_pool)
        
        session.run("""
            MATCH (a:Attorney {id: $attorney_id})
            MATCH (b:BodyShop {id: $bodyshop_id})
            MATCH (adj:Person:Adjuster {id: $adjuster_id})
            CREATE (c:Claim {
                id: $claim_id,
                name: $claim_name,
                claim_amount: $amount,
                claim_date: $claim_date,
                claim_type: 'Auto',
                is_fraud: false
            })
            CREATE (claimant:Person:Claimant {
                id: $claimant_id,
                name: $claimant_name,
                ssn: $ssn,
                phone: $phone
            })
            CREATE (c)-[:FILED_BY]->(claimant)
            CREATE (c)-[:REPRESENTED_BY]->(a)
            CREATE (c)-[:REPAIRED_AT]->(b)
            CREATE (c)-[:HANDLED_BY]->(adj)
            """,
            attorney_id=attorney_id,
            bodyshop_id=bodyshop_id,
            adjuster_id=adjuster_id,
            claim_id=claim_id,
            claim_name=f"Auto Claim {claim_id}",
            amount=round(random.uniform(8000, 25000), 2),
            claim_date=self.generate_date(120, 0),
            claimant_id=claimant_id,
            claimant_name=claimant_name,
            ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
    
    def _create_implicit_staged_tier1(self, count):
        """Tier 1 Staged Accident: 2 shared claims (at threshold)"""
        if count == 0:
            return
        
        print(f"\n   Creating {count} Tier 1 Staged Accidents (borderline: 2 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                # Create 2-3 conspirators
                conspirators = []
                for j in range(random.randint(2, 3)):
                    conspirator_id = f"P_{self.person_counter:05d}"
                    conspirator_name = self.generate_name()
                    self.person_counter += 1
                    conspirators.append(conspirator_id)
                    
                    session.run("""
                        CREATE (p:Person:Claimant {
                            id: $person_id,
                            name: $person_name,
                            ssn: $ssn,
                            phone: $phone
                        })
                        """,
                        person_id=conspirator_id,
                        person_name=conspirator_name,
                        ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                        phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create exactly 2 overlapping claims
                for acc in range(2):
                    self._create_implicit_staged_claim(session, conspirators)
        
        self.generation_stats['implicit_fraud']['tier1']['staged'] = count
    
    def _create_implicit_staged_tier2(self, count):
        """Tier 2 Staged Accident: 3-4 shared claims (moderate)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 2 Staged Accidents (moderate: 3-4 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                # Create 3-4 conspirators
                conspirators = []
                for j in range(random.randint(3, 4)):
                    conspirator_id = f"P_{self.person_counter:05d}"
                    conspirator_name = self.generate_name()
                    self.person_counter += 1
                    conspirators.append(conspirator_id)
                    
                    session.run("""
                        CREATE (p:Person:Claimant {
                            id: $person_id,
                            name: $person_name,
                            ssn: $ssn,
                            phone: $phone
                        })
                        """,
                        person_id=conspirator_id,
                        person_name=conspirator_name,
                        ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                        phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create 3-4 overlapping claims
                num_claims = random.randint(3, 4)
                for acc in range(num_claims):
                    self._create_implicit_staged_claim(session, conspirators)
        
        self.generation_stats['implicit_fraud']['tier2']['staged'] = count
    
    def _create_implicit_staged_tier3(self, count):
        """Tier 3 Staged Accident: 5-6 shared claims (obvious)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 3 Staged Accidents (obvious: 5-6 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                # Create 4-5 conspirators
                conspirators = []
                for j in range(random.randint(4, 5)):
                    conspirator_id = f"P_{self.person_counter:05d}"
                    conspirator_name = self.generate_name()
                    self.person_counter += 1
                    conspirators.append(conspirator_id)
                    
                    session.run("""
                        CREATE (p:Person:Claimant {
                            id: $person_id,
                            name: $person_name,
                            ssn: $ssn,
                            phone: $phone
                        })
                        """,
                        person_id=conspirator_id,
                        person_name=conspirator_name,
                        ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                        phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create 5-6 overlapping claims
                num_claims = random.randint(5, 6)
                for acc in range(num_claims):
                    self._create_implicit_staged_claim(session, conspirators)
        
        self.generation_stats['implicit_fraud']['tier3']['staged'] = count
    
    def _create_implicit_staged_claim(self, session, conspirators):
        """Helper to create a staged accident claim with overlapping participants"""
        claim_id = f"CLM_{self.claim_counter:05d}"
        self.claim_counter += 1
        
        adjuster_id = random.choice(self.adjuster_pool)
        
        # Select 2+ participants from conspirators
        num_participants = min(len(conspirators), random.randint(2, len(conspirators)))
        participants = random.sample(conspirators, num_participants)
        
        session.run("""
            MATCH (adj:Person:Adjuster {id: $adjuster_id})
            CREATE (c:Claim {
                id: $claim_id,
                name: $claim_name,
                claim_amount: $amount,
                claim_date: $claim_date,
                claim_type: 'Auto',
                is_fraud: false
            })
            CREATE (c)-[:HANDLED_BY]->(adj)
            """,
            adjuster_id=adjuster_id,
            claim_id=claim_id,
            claim_name=f"Auto Accident Claim {claim_id}",
            amount=round(random.uniform(10000, 35000), 2),
            claim_date=self.generate_date(180, 30))
        
        # Link participants
        for idx, person_id in enumerate(participants):
            role = "FILED_BY" if idx == 0 else "WITNESSED_BY"
            session.run(f"""
                MATCH (c:Claim {{id: $claim_id}})
                MATCH (p:Person {{id: $person_id}})
                CREATE (c)-[:{role}]->(p)
                """,
                claim_id=claim_id,
                person_id=person_id)
    
    def _create_implicit_phantom_tier1(self, count):
        """Tier 1 Phantom Passenger: 2 connections (below default threshold of 3)"""
        if count == 0:
            return
        
        print(f"\n   Creating {count} Tier 1 Phantom Passengers (borderline: 2 connections)...")
        
        with self.driver.session() as session:
            for i in range(count):
                # Create main claimant (hub)
                main_id = f"P_{self.person_counter:05d}"
                main_name = self.generate_name()
                self.person_counter += 1
                
                session.run("""
                    CREATE (p:Person:Claimant {
                        id: $person_id,
                        name: $person_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    """,
                    person_id=main_id,
                    person_name=main_name,
                    ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create 2 connected phantoms
                for j in range(2):
                    self._create_implicit_phantom_claim(session, main_id)
        
        self.generation_stats['implicit_fraud']['tier1']['phantom'] = count
    
    def _create_implicit_phantom_tier2(self, count):
        """Tier 2 Phantom Passenger: 3-4 connections (at/above threshold)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 2 Phantom Passengers (moderate: 3-4 connections)...")
        
        with self.driver.session() as session:
            for i in range(count):
                main_id = f"P_{self.person_counter:05d}"
                main_name = self.generate_name()
                self.person_counter += 1
                
                session.run("""
                    CREATE (p:Person:Claimant {
                        id: $person_id,
                        name: $person_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    """,
                    person_id=main_id,
                    person_name=main_name,
                    ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create 3-4 connected phantoms
                num_phantoms = random.randint(3, 4)
                for j in range(num_phantoms):
                    self._create_implicit_phantom_claim(session, main_id)
        
        self.generation_stats['implicit_fraud']['tier2']['phantom'] = count
    
    def _create_implicit_phantom_tier3(self, count):
        """Tier 3 Phantom Passenger: 5-7 connections (obvious)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 3 Phantom Passengers (obvious: 5-7 connections)...")
        
        with self.driver.session() as session:
            for i in range(count):
                main_id = f"P_{self.person_counter:05d}"
                main_name = self.generate_name()
                self.person_counter += 1
                
                session.run("""
                    CREATE (p:Person:Claimant {
                        id: $person_id,
                        name: $person_name,
                        ssn: $ssn,
                        phone: $phone
                    })
                    """,
                    person_id=main_id,
                    person_name=main_name,
                    ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")
                
                # Create 5-7 connected phantoms
                num_phantoms = random.randint(5, 7)
                for j in range(num_phantoms):
                    self._create_implicit_phantom_claim(session, main_id)
        
        self.generation_stats['implicit_fraud']['tier3']['phantom'] = count
    
    def _create_implicit_phantom_claim(self, session, main_claimant_id):
        """Helper to create a phantom passenger claim connected to main claimant"""
        phantom_id = f"P_{self.person_counter:05d}"
        phantom_name = self.generate_name()
        self.person_counter += 1
        
        claim_id = f"CLM_{self.claim_counter:05d}"
        self.claim_counter += 1
        
        adjuster_id = random.choice(self.adjuster_pool)
        
        session.run("""
            MATCH (main:Person {id: $main_id})
            MATCH (adj:Person:Adjuster {id: $adjuster_id})
            CREATE (phantom:Person:Claimant {
                id: $phantom_id,
                name: $phantom_name,
                ssn: $ssn,
                phone: $phone
            })
            CREATE (c:Claim {
                id: $claim_id,
                name: $claim_name,
                claim_amount: $amount,
                claim_date: $claim_date,
                claim_type: 'Auto',
                is_fraud: false
            })
            CREATE (c)-[:FILED_BY]->(phantom)
            CREATE (c)-[:HANDLED_BY]->(adj)
            CREATE (phantom)-[:KNOWS]->(main)
            """,
            main_id=main_claimant_id,
            adjuster_id=adjuster_id,
            phantom_id=phantom_id,
            phantom_name=phantom_name,
            ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
            claim_id=claim_id,
            claim_name=f"Auto Claim {claim_id}",
            amount=round(random.uniform(8000, 28000), 2),
            claim_date=self.generate_date(150, 20))
    
    def _create_implicit_adjuster_collusion_tier1(self, count):
        """Tier 1 Adjuster Collusion: 3 shared claims (below default threshold of 4)"""
        if count == 0:
            return
        
        print(f"\n   Creating {count} Tier 1 Adjuster Collusion (borderline: 3 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                # Create dedicated adjuster for this pattern
                adjuster_id = f"ADJ_IMP_T1_{i:05d}_{self.adjuster_counter:05d}"
                adjuster_name = self.generate_name()
                self.adjuster_counter += 1
                
                # Create provider
                provider_id = f"MED_IMP_AC_T1_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Neighborhood Clinic {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (adj:Person:Adjuster {
                        id: $adjuster_id,
                        name: $adjuster_name,
                        employee_id: $employee_id
                    })
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    adjuster_id=adjuster_id,
                    adjuster_name=adjuster_name,
                    employee_id=f"EMP-{self.adjuster_counter:05d}",
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 3 shared claims (below threshold)
                for j in range(3):
                    self._create_implicit_adjuster_collusion_claim(session, adjuster_id, provider_id)
        
        self.generation_stats['implicit_fraud']['tier1']['adjuster_collusion'] = count
    
    def _create_implicit_adjuster_collusion_tier2(self, count):
        """Tier 2 Adjuster Collusion: 4-5 shared claims (at/above threshold)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 2 Adjuster Collusion (moderate: 4-5 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                adjuster_id = f"ADJ_IMP_T2_{i:05d}_{self.adjuster_counter:05d}"
                adjuster_name = self.generate_name()
                self.adjuster_counter += 1
                
                provider_id = f"MED_IMP_AC_T2_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Metro Health Services {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (adj:Person:Adjuster {
                        id: $adjuster_id,
                        name: $adjuster_name,
                        employee_id: $employee_id
                    })
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    adjuster_id=adjuster_id,
                    adjuster_name=adjuster_name,
                    employee_id=f"EMP-{self.adjuster_counter:05d}",
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 4-5 shared claims
                num_claims = random.randint(4, 5)
                for j in range(num_claims):
                    self._create_implicit_adjuster_collusion_claim(session, adjuster_id, provider_id)
        
        self.generation_stats['implicit_fraud']['tier2']['adjuster_collusion'] = count
    
    def _create_implicit_adjuster_collusion_tier3(self, count):
        """Tier 3 Adjuster Collusion: 6-8 shared claims (obvious)"""
        if count == 0:
            return
        
        print(f"   Creating {count} Tier 3 Adjuster Collusion (obvious: 6-8 shared claims)...")
        
        with self.driver.session() as session:
            for i in range(count):
                adjuster_id = f"ADJ_IMP_T3_{i:05d}_{self.adjuster_counter:05d}"
                adjuster_name = self.generate_name()
                self.adjuster_counter += 1
                
                provider_id = f"MED_IMP_AC_T3_{i:05d}_{self.provider_counter:05d}"
                provider_name = f"Premium Care Institute {i}"
                self.provider_counter += 1
                
                session.run("""
                    CREATE (adj:Person:Adjuster {
                        id: $adjuster_id,
                        name: $adjuster_name,
                        employee_id: $employee_id
                    })
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license
                    })
                    """,
                    adjuster_id=adjuster_id,
                    adjuster_name=adjuster_name,
                    employee_id=f"EMP-{self.adjuster_counter:05d}",
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 6-8 shared claims
                num_claims = random.randint(6, 8)
                for j in range(num_claims):
                    self._create_implicit_adjuster_collusion_claim(session, adjuster_id, provider_id)
        
        self.generation_stats['implicit_fraud']['tier3']['adjuster_collusion'] = count
    
    def _create_implicit_adjuster_collusion_claim(self, session, adjuster_id, provider_id):
        """Helper to create an adjuster-provider collusion claim"""
        claim_id = f"CLM_{self.claim_counter:05d}"
        self.claim_counter += 1
        
        claimant_id = f"P_{self.person_counter:05d}"
        claimant_name = self.generate_name()
        self.person_counter += 1
        
        session.run("""
            MATCH (adj:Person:Adjuster {id: $adjuster_id})
            MATCH (m:MedicalProvider {id: $provider_id})
            CREATE (c:Claim {
                id: $claim_id,
                name: $claim_name,
                claim_amount: $amount,
                claim_date: $claim_date,
                claim_type: 'Medical',
                is_fraud: false
            })
            CREATE (claimant:Person:Claimant {
                id: $claimant_id,
                name: $claimant_name,
                ssn: $ssn,
                phone: $phone
            })
            CREATE (c)-[:FILED_BY]->(claimant)
            CREATE (c)-[:TREATED_AT]->(m)
            CREATE (c)-[:HANDLED_BY]->(adj)
            """,
            adjuster_id=adjuster_id,
            provider_id=provider_id,
            claim_id=claim_id,
            claim_name=f"Medical Claim {claim_id}",
            amount=round(random.uniform(10000, 35000), 2),
            claim_date=self.generate_date(120, 0),
            claimant_id=claimant_id,
            claimant_name=claimant_name,
            ssn=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            phone=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

    def _print_implicit_fraud_summary(self):
        """Print summary of implicit fraud patterns created"""
        stats = self.generation_stats['implicit_fraud']
        
        print(f"\n   {'─'*50}")
        print(f"   Implicit Fraud Summary:")
        print(f"   {'─'*50}")
        
        for fraud_type in ['medical_mill', 'kickback', 'staged', 'phantom', 'adjuster_collusion']:
            t1 = stats['tier1'].get(fraud_type, 0)
            t2 = stats['tier2'].get(fraud_type, 0)
            t3 = stats['tier3'].get(fraud_type, 0)
            total = t1 + t2 + t3
            
            if total > 0:
                print(f"   {fraud_type.replace('_', ' ').title()}: {total} total")
                print(f"      Tier 1 (borderline): {t1}")
                print(f"      Tier 2 (moderate):   {t2}")
                print(f"      Tier 3 (obvious):    {t3}")

    # =========================================================================
    # NEAR-MISS LEGITIMATE PATTERNS (False positive testing)
    # =========================================================================
    
    def create_near_miss_legitimate_patterns(self, config=None):
        """
        Create borderline legitimate patterns that might trigger false positives.
        These help test the precision of detection algorithms.
        
        Args:
            config: Dict with counts for each pattern type
        """
        if config is None:
            config = {
                'high_volume_providers': 3,
                'repeat_referrals': 2,
                'repeat_witnesses': 3
            }
        
        print(f"\n{'='*60}")
        print("Creating Near-Miss Legitimate Patterns (false positive testing)")
        print(f"{'='*60}")
        
        self._create_high_volume_legitimate_providers(config.get('high_volume_providers', 0))
        self._create_repeat_legitimate_referrals(config.get('repeat_referrals', 0))
        self._create_repeat_legitimate_witnesses(config.get('repeat_witnesses', 0))
        
        print(f"\n   Near-miss patterns created:")
        for k, v in self.generation_stats['near_miss_legitimate'].items():
            print(f"      {k.replace('_', ' ').title()}: {v}")
    
    def _create_high_volume_legitimate_providers(self, count):
        """
        Create high-volume but legitimate medical providers.
        Example: Busy emergency rooms, popular clinics in high-traffic areas.
        These have 4-5 claims (near threshold) but are legitimate.
        """
        if count == 0:
            return
        
        print(f"\n   Creating {count} high-volume legitimate providers...")
        
        legitimate_provider_names = [
            "City General Hospital ER",
            "Downtown Urgent Care",
            "Interstate Highway Trauma Center",
            "University Medical Center",
            "Regional Sports Medicine Clinic"
        ]
        
        with self.driver.session() as session:
            for i in range(count):
                provider_id = f"MED_LEGIT_{i:05d}_{self.provider_counter:05d}"
                provider_name = legitimate_provider_names[i % len(legitimate_provider_names)]
                self.provider_counter += 1
                
                session.run("""
                    CREATE (m:MedicalProvider {
                        id: $provider_id,
                        name: $provider_name,
                        license: $license,
                        legitimate_high_volume: true
                    })
                    """,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    license=f"MED-LIC-{random.randint(10000, 99999)}")
                
                # 4-5 claims (near threshold but legitimate)
                # Lower claim amounts than fraud (realistic ER visits)
                num_claims = random.randint(4, 5)
                for j in range(num_claims):
                    self._create_implicit_medical_claim(session, provider_id,
                                                        amount_range=(5000, 15000))
        
        self.generation_stats['near_miss_legitimate']['high_volume_providers'] = count
    
    def _create_repeat_legitimate_referrals(self, count):
        """
        Create legitimate attorney-bodyshop referral relationships.
        Example: Attorney who specializes in auto accidents and recommends
        a quality bodyshop. Has 2 shared claims (below threshold).
        """
        if count == 0:
            return
        
        print(f"   Creating {count} legitimate repeat referral patterns...")
        
        with self.driver.session() as session:
            for i in range(count):
                attorney_id = f"ATT_LEGIT_{i:05d}_{self.attorney_counter:05d}"
                attorney_name = f"{self.generate_name()}, Esq."
                self.attorney_counter += 1
                
                bodyshop_id = f"BS_LEGIT_{i:05d}_{self.bodyshop_counter:05d}"
                bodyshop_name = f"Certified Collision Experts {i}"
                self.bodyshop_counter += 1
                
                session.run("""
                    CREATE (a:Attorney {
                        id: $attorney_id,
                        name: $attorney_name,
                        bar_number: $bar_number,
                        specialty: 'Auto Accidents',
                        legitimate_referrals: true
                    })
                    CREATE (b:BodyShop {
                        id: $bodyshop_id,
                        name: $bodyshop_name,
                        license: $license,
                        certified: true
                    })
                    """,
                    attorney_id=attorney_id,
                    attorney_name=attorney_name,
                    bar_number=f"BAR-{random.randint(100000, 999999)}",
                    bodyshop_id=bodyshop_id,
                    bodyshop_name=bodyshop_name,
                    license=f"BS-LIC-{random.randint(10000, 99999)}")
                
                # Only 2 shared claims (below threshold - legitimate referral)
                for j in range(2):
                    self._create_implicit_kickback_claim(session, attorney_id, bodyshop_id)
        
        self.generation_stats['near_miss_legitimate']['repeat_referrals'] = count
    
    def _create_repeat_legitimate_witnesses(self, count):
        """
        Create legitimate cases where same people appear in multiple claims.
        Example: Family members, coworkers who commute together, neighbors.
        These have 2 shared claims (at threshold) but are legitimate.
        """
        if count == 0:
            return
        
        print(f"   Creating {count} legitimate repeat witness patterns...")
        
        relationships = ["family", "coworkers", "neighbors", "carpool"]
        
        with self.driver.session() as session:
            for i in range(count):
                relationship = relationships[i % len(relationships)]
                
                # Create 2 related people
                person1_id = f"P_{self.person_counter:05d}"
                person1_name = self.generate_name()
                self.person_counter += 1
                
                person2_id = f"P_{self.person_counter:05d}"
                # Same last name for family
                if relationship == "family":
                    last_name = person1_name.split()[1]
                    person2_name = f"{self.generate_name().split()[0]} {last_name}"
                else:
                    person2_name = self.generate_name()
                self.person_counter += 1
                
                session.run("""
                    CREATE (p1:Person:Claimant {
                        id: $person1_id,
                        name: $person1_name,
                        ssn: $ssn1,
                        phone: $phone1,
                        legitimate_relationship: $relationship
                    })
                    CREATE (p2:Person:Claimant {
                        id: $person2_id,
                        name: $person2_name,
                        ssn: $ssn2,
                        phone: $phone2,
                        legitimate_relationship: $relationship
                    })
                    """,
                    person1_id=person1_id,
                    person1_name=person1_name,
                    ssn1=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    phone1=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                    person2_id=person2_id,
                    person2_name=person2_name,
                    ssn2=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
                    phone2=f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                    relationship=relationship)
                
                # Create 2 claims where both appear (at threshold - legitimate)
                for j in range(2):
                    claim_id = f"CLM_{self.claim_counter:05d}"
                    self.claim_counter += 1
                    
                    adjuster_id = random.choice(self.adjuster_pool)
                    
                    session.run("""
                        MATCH (p1:Person {id: $person1_id})
                        MATCH (p2:Person {id: $person2_id})
                        MATCH (adj:Person:Adjuster {id: $adjuster_id})
                        CREATE (c:Claim {
                            id: $claim_id,
                            name: $claim_name,
                            claim_amount: $amount,
                            claim_date: $claim_date,
                            claim_type: 'Auto',
                            is_fraud: false,
                            legitimate_shared_claim: true
                        })
                        CREATE (c)-[:FILED_BY]->(p1)
                        CREATE (c)-[:WITNESSED_BY]->(p2)
                        CREATE (c)-[:HANDLED_BY]->(adj)
                        """,
                        person1_id=person1_id,
                        person2_id=person2_id,
                        adjuster_id=adjuster_id,
                        claim_id=claim_id,
                        claim_name=f"Legitimate Shared Claim {claim_id}",
                        amount=round(random.uniform(5000, 20000), 2),
                        claim_date=self.generate_date(200, 30))
        
        self.generation_stats['near_miss_legitimate']['repeat_witnesses'] = count

    # =========================================================================
    # LEGACY SUPPORT: Old implicit fraud method (maps to tiered)
    # =========================================================================
    
    def create_implicit_fraud_patterns(self, pattern_config=None):
        """
        Legacy method - maps to tiered generation for backward compatibility.
        
        Args:
            pattern_config: Dict with counts for each fraud type
                           Maps to tier2 (moderate) patterns for default behavior
        """
        if pattern_config is None:
            pattern_config = {
                'medical_mill': 2,
                'kickback': 1,
                'staged': 1,
                'phantom': 1
            }
        
        # Map to tiered config (distribute across tiers)
        tier_config = {}
        for fraud_type, count in pattern_config.items():
            if count > 0:
                # Distribute: 40% tier1, 40% tier2, 20% tier3
                t1 = max(1, int(count * 0.4))
                t2 = max(1, int(count * 0.4))
                t3 = max(0, count - t1 - t2)
                tier_config[fraud_type] = {'tier1': t1, 'tier2': t2, 'tier3': t3}
            else:
                tier_config[fraud_type] = {'tier1': 0, 'tier2': 0, 'tier3': 0}
        
        self.create_tiered_implicit_fraud_patterns(tier_config)

    # =========================================================================
    # MAIN GENERATION METHODS
    # =========================================================================

    def generate_all_data(self, include_near_miss=True):
        """
        Generate complete dataset with proper initialization.
        
        Args:
            include_near_miss: Whether to include near-miss legitimate patterns
        """
        print("=" * 60)
        print("INSURANCE FRAUD DETECTION DATA GENERATOR")
        print("=" * 60)

        self.clear_database()
        self.create_indexes()
        
        # Create shared entity pools FIRST
        self.create_adjuster_pool(num_adjusters=20)
        self.create_service_provider_pools()

        # Generate legitimate claims
        self.create_legitimate_claims(num_claims=150)
        
        # Generate explicit fraud patterns (labeled)
        self.create_medical_mill(num_rings=3)
        self.create_bodyshop_kickback(num_rings=3)
        self.create_staged_accident(num_rings=2)
        self.create_phantom_passenger(num_rings=3)
        
        # Generate tiered implicit patterns (unlabeled)
        tier_config = {
            'medical_mill': {'tier1': 2, 'tier2': 2, 'tier3': 1},
            'kickback': {'tier1': 2, 'tier2': 1, 'tier3': 1},
            'staged': {'tier1': 2, 'tier2': 1, 'tier3': 1},
            'phantom': {'tier1': 2, 'tier2': 1, 'tier3': 1}
        }
        self.create_tiered_implicit_fraud_patterns(tier_config)
        
        # Generate near-miss legitimate patterns
        if include_near_miss:
            near_miss_config = {
                'high_volume_providers': 3,
                'repeat_referrals': 2,
                'repeat_witnesses': 3
            }
            self.create_near_miss_legitimate_patterns(near_miss_config)

        self._print_final_summary()

    def _print_final_summary(self):
        """Print comprehensive generation summary"""
        print("\n" + "=" * 60)
        print("DATA GENERATION COMPLETE!")
        print("=" * 60)

        with self.driver.session() as session:
            result = session.run("""
            MATCH (c:Claim)
            RETURN 
                count(c) as total_claims,
                sum(CASE WHEN c.is_fraud THEN 1 ELSE 0 END) as fraud_claims,
                sum(CASE WHEN NOT c.is_fraud THEN 1 ELSE 0 END) as legitimate_claims
            """)
            stats = result.single()

            print(f"\n📊 Data Summary:")
            print(f"   Total Claims: {stats['total_claims']}")
            print(f"   Labeled Fraud Claims: {stats['fraud_claims']}")
            print(f"   Unlabeled Claims: {stats['legitimate_claims']}")

            result = session.run("MATCH (p:Person) RETURN count(p) as count")
            print(f"   Total Persons: {result.single()['count']}")

            result = session.run("MATCH (m:MedicalProvider) RETURN count(m) as count")
            print(f"   Medical Providers: {result.single()['count']}")

            result = session.run("MATCH (a:Attorney) RETURN count(a) as count")
            print(f"   Attorneys: {result.single()['count']}")

            result = session.run("MATCH (b:BodyShop) RETURN count(b) as count")
            print(f"   Body Shops: {result.single()['count']}")
            
            # Detection hint
            print(f"\n💡 Detection Hints:")
            print(f"   Default thresholds will detect: Tier 2 + Tier 3 patterns")
            print(f"   Lower thresholds to reveal: Tier 1 (borderline) patterns")
            print(f"   Near-miss patterns may cause false positives at low thresholds")


if __name__ == "__main__":
    print("This module is designed to run within Streamlit.")
    print("Run: streamlit run app.py")