"""
Main app code for Streamlit UI - ENHANCED VERSION
Phase 1: Visual Impact Improvements
"""
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config
from neo4j import GraphDatabase
import pandas as pd
import sys
import io
import time
from datetime import datetime, timedelta
import random


# Import custom modules
from fraud_detection import FraudDetector
from data_generator import FraudDataGenerator

# -----------------------------------------------------------------------------
# Performance tracking utility
# -----------------------------------------------------------------------------
class PerformanceTimer:
    """Track query performance for demo purposes"""
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.duration_ms = None
        self.entity_count = 0
        self.relationship_count = 0
    
    def start(self):
        self.start_time = time.time()
    
    def stop(self):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        return self.duration_ms
    
    def set_counts(self, entities, relationships):
        self.entity_count = entities
        self.relationship_count = relationships
    
    def get_duration(self):
        """Get duration in milliseconds"""
        return self.duration_ms if self.duration_ms else 0
    
    def get_summary(self):
        return {
            'duration_ms': self.duration_ms if self.duration_ms else 0,
            'entities': self.entity_count,
            'relationships': self.relationship_count
        }

# -----------------------------------------------------------------------------
# Enhanced color utilities
# -----------------------------------------------------------------------------
def get_color_gradient(score, base_color):
    """
    Generate color gradient based on suspicion score (0-100)
    Uses ORANGE spectrum only - RED is reserved for confirmed fraud
    """
    if score >= 80:
        return "#D35400"  # Dark orange - Critical suspicion (NOT red)
    elif score >= 60:
        return "#E67E22"  # Orange - High suspicion
    elif score >= 40:
        return "#F39C12"  # Amber - Medium suspicion
    elif score >= 20:
        return "#F1C40F"  # Yellow - Low suspicion
    else:
        return base_color  # Base color - Minimal suspicion

def display_performance_metrics(timer, query_type="Query"):
    """Display query performance metrics in an attractive format"""
    metrics = timer.get_summary()
    
    st.markdown("---")
    st.markdown(f"### 🚀 Graph DB Performance - {query_type}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "⚡ Execution Time",
            f"{metrics['duration_ms']} ms",
            help="Time to traverse the graph and return results"
        )
    
    with col2:
        st.metric(
            "🔍 Entities Found",
            f"{metrics['entities']}",
            help="Total nodes discovered in the network"
        )
    
    with col3:
        st.metric(
            "🔗 Relationships",
            f"{metrics['relationships']}",
            help="Connections traversed in the graph"
        )
    
    with col4:
        # Calculate effective traversal rate
        if metrics['duration_ms'] > 0:
            rate = round((metrics['entities'] + metrics['relationships']) / (metrics['duration_ms'] / 1000), 0)
            st.metric(
                "📊 Traversal Rate",
                f"{rate}/sec",
                help="Entities + relationships processed per second"
            )
        else:
            st.metric("📊 Traversal Rate", "N/A")

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Insurance Fraud Detection",
    layout="wide",
    page_icon="🔍"
)

# Initialize session state for admin operations
if 'admin_message' not in st.session_state:
    st.session_state.admin_message = None
if 'admin_message_type' not in st.session_state:
    st.session_state.admin_message_type = None
if 'generation_log' not in st.session_state:
    st.session_state.generation_log = None

# -----------------------------------------------------------------------------
# Neo4j Connection
# -----------------------------------------------------------------------------
@st.cache_resource
def get_neo4j_driver():
    try:
        uri = st.secrets["neo4j"]["uri"]
        user = st.secrets["neo4j"]["user"]
        password = st.secrets["neo4j"]["password"]

        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver

    except KeyError:
        st.error("❌ Neo4j secrets not found. Check `.streamlit/secrets.toml`")
        st.info("""
        Create `.streamlit/secrets.toml` with:
        ```toml
        [neo4j]
        uri = "neo4j+s://your-instance.databases.neo4j.io"
        user = "neo4j"
        password = "your-password"
        ```
        """)
        return None

    except Exception as e:
        st.error(f"❌ Failed to connect to Neo4j: {e}")
        return None


driver = get_neo4j_driver()
if driver is None:
    st.stop()

# -----------------------------------------------------------------------------
# Data access helpers
# -----------------------------------------------------------------------------
def get_entity_types(driver):
    with driver.session() as session:
        result = session.run("CALL db.labels()")
        return sorted([r[0] for r in result])


def get_entities_by_type(driver, entity_type):
    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (n:{entity_type})
            RETURN n.id AS id, n.name AS name
            ORDER BY n.name
            LIMIT 1000
            """
        )
        return [(r["id"], r.get("name", r["id"])) for r in result]


def get_neighborhood(driver, entity_type, entity_id, hops, entity_filters):
    """
    Get connected neighborhood starting from root entity.
    Returns only nodes connected to the root within specified hops.
    """
    with driver.session() as session:
        # Build filter clause for entity types
        if entity_filters:
            filter_clause = " OR ".join([f"'{l}' IN labels(m)" for l in entity_filters])
        else:
            filter_clause = "true"
        
        # Query to get ALL paths from root node within N hops
        # This ensures we only get connected components containing the root
        query = f"""
        MATCH path = (root:{entity_type} {{id: $entity_id}})-[*1..{hops}]-(m)
        WHERE {filter_clause}
        
        // Collect all unique nodes and relationships in these paths
        WITH collect(path) as paths
        UNWIND paths as p
        UNWIND relationships(p) as rel
        
        WITH DISTINCT rel,
             startNode(rel) as start,
             endNode(rel) as end
        
        RETURN DISTINCT
            id(start) AS source_id,
            labels(start) AS source_labels,
            properties(start) AS source_props,
            type(rel) AS rel_type,
            id(end) AS target_id,
            labels(end) AS target_labels,
            properties(end) AS target_props
        """

        return list(session.run(query, entity_id=entity_id))


def get_fraud_rings(driver, fraud_type=None):
    """Get known fraud rings from labeled data"""
    with driver.session() as session:
        if fraud_type and fraud_type != "All":
            query = """
            MATCH (c:Claim {is_fraud: true, fraud_type: $fraud_type})
            MATCH path = (c)-[*1..3]-(n)
            WHERE n.id <> c.id
            WITH collect(path) as paths
            UNWIND paths as p
            UNWIND relationships(p) as rel
            WITH DISTINCT rel,
                 startNode(rel) as start,
                 endNode(rel) as end
            RETURN DISTINCT
                id(start) AS source_id,
                labels(start) AS source_labels,
                properties(start) AS source_props,
                type(rel) AS rel_type,
                id(end) AS target_id,
                labels(end) AS target_labels,
                properties(end) AS target_props
            LIMIT 500
            """
            result = session.run(query, fraud_type=fraud_type)
        else:
            query = """
            MATCH (c:Claim {is_fraud: true})
            MATCH path = (c)-[*1..2]-(n)
            WHERE n.id <> c.id
            WITH collect(path) as paths
            UNWIND paths as p
            UNWIND relationships(p) as rel
            WITH DISTINCT rel,
                 startNode(rel) as start,
                 endNode(rel) as end
            RETURN DISTINCT
                id(start) AS source_id,
                labels(start) AS source_labels,
                properties(start) AS source_props,
                type(rel) AS rel_type,
                id(end) AS target_id,
                labels(end) AS target_labels,
                properties(end) AS target_props
            LIMIT 500
            """
            result = session.run(query)
        
        return list(result)


def get_individual_fraud_rings(driver, fraud_type):
    """Get list of individual fraud rings with metadata for selection"""
    with driver.session() as session:
        # Get fraud claims grouped by connected components
        query = """
        MATCH (c:Claim {is_fraud: true, fraud_type: $fraud_type})
        WITH c
        ORDER BY c.id
        WITH collect(c) as fraud_claims
        
        UNWIND fraud_claims as claim
        MATCH (claim)-[*1..2]-(connected)
        WHERE connected.is_fraud = true
        WITH claim, collect(DISTINCT connected.id) as ring_members
        WITH claim.id as claim_id, 
             claim.name as claim_name,
             claim.claim_amount as amount,
             size(ring_members) as ring_size
        ORDER BY ring_size DESC, amount DESC
        RETURN claim_id, claim_name, amount, ring_size
        """
        
        result = session.run(query, fraud_type=fraud_type)
        rings = []
        
        for r in result:
            rings.append({
                'claim_id': r['claim_id'],
                'claim_name': r['claim_name'],
                'amount': r['amount'],
                'ring_size': r['ring_size']
            })
        
        return rings


def get_fraud_ring_neighborhood(driver, root_claim_id, hops=2):
    """Get neighborhood of a specific fraud ring starting from a root claim"""
    with driver.session() as session:
        query = f"""
        MATCH path = (root:Claim {{id: $claim_id}})-[*1..{hops}]-(connected)
        WHERE connected.id <> root.id
        
        WITH collect(path) as paths
        UNWIND paths as p
        UNWIND relationships(p) as rel
        
        WITH DISTINCT rel,
             startNode(rel) as start,
             endNode(rel) as end
        
        RETURN DISTINCT
            id(start) AS source_id,
            labels(start) AS source_labels,
            properties(start) AS source_props,
            type(rel) AS rel_type,
            id(end) AS target_id,
            labels(end) AS target_labels,
            properties(end) AS target_props
        """
        
        return list(session.run(query, claim_id=root_claim_id))


def get_suspicious_communities(driver):
    """Get detected suspicious entities"""
    with driver.session() as session:
        query = """
        MATCH (n)
        WHERE n.suspicious = true
        WITH n
        MATCH path = (n)-[*1..2]-(m)
        WHERE m.id <> n.id
        WITH collect(path) as paths
        UNWIND paths as p
        UNWIND relationships(p) as rel
        WITH DISTINCT rel,
             startNode(rel) as start,
             endNode(rel) as end
        RETURN DISTINCT
            id(start) AS source_id,
            labels(start) AS source_labels,
            properties(start) AS source_props,
            type(rel) AS rel_type,
            id(end) AS target_id,
            labels(end) AS target_labels,
            properties(end) AS target_props
        LIMIT 500
        """
        return list(session.run(query))


def get_database_stats(driver):
    """Get comprehensive database statistics"""
    with driver.session() as session:
        # Node counts by label
        node_stats = session.run("""
        MATCH (n)
        RETURN labels(n)[0] as label, count(n) as count
        ORDER BY count DESC
        """).data()
        
        # Fraud statistics
        fraud_stats = session.run("""
        MATCH (c:Claim)
        RETURN 
            count(c) as total_claims,
            sum(CASE WHEN c.is_fraud THEN 1 ELSE 0 END) as fraud_claims,
            sum(CASE WHEN NOT c.is_fraud THEN 1 ELSE 0 END) as legitimate_claims
        """).single()
        
        # Suspicious entity count
        suspicious_count = session.run("""
        MATCH (n) WHERE n.suspicious = true
        RETURN count(n) as count
        """).single()
        
        # Total relationship count
        rel_count = session.run("""
        MATCH ()-[r]->()
        RETURN count(r) as count
        """).single()
        
        return {
            'node_stats': node_stats,
            'fraud_stats': fraud_stats,
            'suspicious_count': suspicious_count['count'] if suspicious_count else 0,
            'relationship_count': rel_count['count'] if rel_count else 0
        }

def get_existing_claimants(driver, limit=100):
    """Get existing claimants for dropdown selection"""
    with driver.session() as session:
        result = session.run("""
            MATCH (p:Person:Claimant)
            OPTIONAL MATCH (p)<-[:FILED_BY]-(c:Claim)
            WITH p, count(c) as claim_count,
                 CASE WHEN p.is_fraud = true THEN '🔴 '
                      WHEN p.suspicious = true THEN '🟠 '
                      ELSE '' END as flag
            RETURN p.id as id, 
                   p.name as name,
                   flag,
                   claim_count
            ORDER BY p.suspicious DESC, p.is_fraud DESC, p.name
            LIMIT $limit
        """, limit=limit)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['claim_count']} claims)") for r in result]


def get_existing_witnesses(driver, limit=100):
    """Get existing witnesses for dropdown selection"""
    with driver.session() as session:
        result = session.run("""
            MATCH (p:Person:Witness)
            OPTIONAL MATCH (p)<-[:WITNESSED_BY]-(c:Claim)
            WITH p, count(c) as claim_count,
                 CASE WHEN p.is_fraud = true THEN '🔴 '
                      WHEN p.suspicious = true THEN '🟠 '
                      ELSE '' END as flag
            RETURN p.id as id, 
                   p.name as name,
                   flag,
                   claim_count
            ORDER BY p.suspicious DESC, p.is_fraud DESC, p.name
            LIMIT $limit
        """, limit=limit)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['claim_count']} cases)") for r in result]


def get_adjuster_pool(driver):
    """Get all adjusters for assignment dropdown"""
    with driver.session() as session:
        result = session.run("""
            MATCH (a:Person:Adjuster)
            OPTIONAL MATCH (a)<-[:HANDLED_BY]-(c:Claim)
            WITH a, count(c) as claim_count,
                 CASE WHEN a.is_fraud = true THEN '🔴 '
                      WHEN a.suspicious = true THEN '🟠 '
                      ELSE '' END as flag
            RETURN a.id as id, 
                   a.name as name,
                   a.employee_id as emp_id,
                   flag,
                   claim_count
            ORDER BY a.suspicious DESC, a.is_fraud DESC, claim_count ASC
        """)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['emp_id']}) - {r['claim_count']} claims") for r in result]


def get_medical_providers(driver):
    """Get medical providers for optional selection"""
    with driver.session() as session:
        result = session.run("""
            MATCH (m:MedicalProvider)
            OPTIONAL MATCH (m)<-[:TREATED_AT]-(c:Claim)
            WITH m, count(c) as claim_count,
                 CASE WHEN m.is_fraud = true THEN '🔴 FRAUD: '
                      WHEN m.suspicious = true THEN '🟠 SUSPICIOUS: '
                      ELSE '' END as flag
            RETURN m.id as id, 
                   m.name as name,
                   flag,
                   claim_count
            ORDER BY m.is_fraud DESC, m.suspicious DESC, claim_count DESC
        """)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['claim_count']} claims)") for r in result]


def get_body_shops(driver):
    """Get body shops for optional selection"""
    with driver.session() as session:
        result = session.run("""
            MATCH (b:BodyShop)
            OPTIONAL MATCH (b)<-[:REPAIRED_AT]-(c:Claim)
            WITH b, count(c) as claim_count,
                 CASE WHEN b.is_fraud = true THEN '🔴 FRAUD: '
                      WHEN b.suspicious = true THEN '🟠 SUSPICIOUS: '
                      ELSE '' END as flag
            RETURN b.id as id, 
                   b.name as name,
                   flag,
                   claim_count
            ORDER BY b.is_fraud DESC, b.suspicious DESC, claim_count DESC
        """)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['claim_count']} claims)") for r in result]


def get_attorneys(driver):
    """Get attorneys for optional selection"""
    with driver.session() as session:
        result = session.run("""
            MATCH (a:Attorney)
            OPTIONAL MATCH (a)<-[:REPRESENTED_BY]-(c:Claim)
            WITH a, count(c) as claim_count,
                 CASE WHEN a.is_fraud = true THEN '🔴 FRAUD: '
                      WHEN a.suspicious = true THEN '🟠 SUSPICIOUS: '
                      ELSE '' END as flag
            RETURN a.id as id, 
                   a.name as name,
                   flag,
                   claim_count
            ORDER BY a.is_fraud DESC, a.suspicious DESC, claim_count DESC
        """)
        return [(r['id'], f"{r['flag']}{r['name']} ({r['claim_count']} cases)") for r in result]


def assess_entity_risk(driver, entity_ids_by_type):
    """
    Assess fraud risk based on selected entities' neighborhoods.
    
    Args:
        entity_ids_by_type: Dict like {'Claimant': 'P_001', 'BodyShop': 'BS_001', ...}
    
    Returns:
        Dict with risk assessment results
    """
    if not entity_ids_by_type:
        return {'score': 0, 'fraud_count': 0, 'suspicious_count': 0, 'warnings': []}
    
    warnings = []
    fraud_entities = []
    suspicious_entities = []
    
    with driver.session() as session:
        for entity_type, entity_id in entity_ids_by_type.items():
            if not entity_id:
                continue
            
            # Check the entity itself
            direct_check = session.run("""
                MATCH (n {id: $entity_id})
                RETURN n.name as name,
                       n.is_fraud as is_fraud,
                       n.suspicious as suspicious,
                       n.suspicion_type as suspicion_type,
                       n.suspicion_score as suspicion_score,
                       n.fraud_type as fraud_type
            """, entity_id=entity_id).single()
            
            if direct_check:
                if direct_check['is_fraud']:
                    fraud_entities.append({
                        'name': direct_check['name'],
                        'type': entity_type,
                        'fraud_type': direct_check['fraud_type']
                    })
                    warnings.append(f"🔴 {entity_type} '{direct_check['name']}' is CONFIRMED FRAUD ({direct_check['fraud_type']})")
                elif direct_check['suspicious']:
                    suspicious_entities.append({
                        'name': direct_check['name'],
                        'type': entity_type,
                        'suspicion_type': direct_check['suspicion_type'],
                        'score': direct_check['suspicion_score']
                    })
                    warnings.append(f"🟠 {entity_type} '{direct_check['name']}' is SUSPICIOUS ({direct_check['suspicion_type']}, Score: {direct_check['suspicion_score']})")
            
            # Check 2-hop neighborhood
            neighborhood_check = session.run("""
                MATCH (n {id: $entity_id})-[*1..2]-(connected)
                WHERE connected.id <> $entity_id
                  AND (connected.is_fraud = true OR connected.suspicious = true)
                RETURN DISTINCT
                       connected.name as name,
                       labels(connected)[0] as type,
                       connected.is_fraud as is_fraud,
                       connected.suspicious as suspicious,
                       connected.fraud_type as fraud_type,
                       connected.suspicion_type as suspicion_type
                LIMIT 10
            """, entity_id=entity_id)
            
            for record in neighborhood_check:
                if record['is_fraud'] and record['name'] not in [f['name'] for f in fraud_entities]:
                    fraud_entities.append({
                        'name': record['name'],
                        'type': record['type'],
                        'fraud_type': record['fraud_type'],
                        'connection': entity_type
                    })
                elif record['suspicious'] and record['name'] not in [s['name'] for s in suspicious_entities]:
                    suspicious_entities.append({
                        'name': record['name'],
                        'type': record['type'],
                        'suspicion_type': record['suspicion_type'],
                        'connection': entity_type
                    })
    
    # Calculate risk score
    risk_score = min(100, (len(fraud_entities) * 30) + (len(suspicious_entities) * 15))
    
    return {
        'score': risk_score,
        'fraud_count': len(fraud_entities),
        'suspicious_count': len(suspicious_entities),
        'fraud_entities': fraud_entities,
        'suspicious_entities': suspicious_entities,
        'warnings': warnings
    }


# -----------------------------------------------------------------------------
# ENHANCED Graph visualization with gradients and better physics
# -----------------------------------------------------------------------------
def get_display_label(labels):
    """
    Get most specific label for visualization.
    Prioritizes role-specific labels over generic ones.
    """
    # Order matters: most specific first
    priority_order = [
        "Claimant", "Witness", "Adjuster",  # Person roles
        "MedicalProvider", "Attorney", "BodyShop",  # Service providers
        "Claim", "Person"  # Generic fallback
    ]
    
    for priority_label in priority_order:
        if priority_label in labels:
            return priority_label
    
    return labels[0] if labels else "Unknown"


def create_graph_visualization(records, entity_filters=None, root_entity_id=None):
    """
    ENHANCED: Create graph visualization with detailed tooltips and better spacing
    
    Args:
        records: Neo4j query results
        entity_filters: List of entity types to include
        root_entity_id: ID of the root node (will be highlighted)
    """
    nodes = {}
    edges = []

    # Enhanced hierarchical color scheme with gradient support
    color_map = {
        # Core entity
        "Claim": "#2C3E50",           # Dark slate gray
        
        # People (blue family - involved parties)
        "Claimant": "#3498DB",        # Bright blue (primary party)
        "Witness": "#5DADE2",         # Light blue (observer)
        
        # Internal (green family - company personnel)
        "Adjuster": "#27AE60",        # Emerald green (employee)
        
        # Service Providers (warm family - but NOT red)
        "MedicalProvider": "#9B59B6",  # Purple
        "Attorney": "#E67E22",         # Dark orange
        "BodyShop": "#F39C12",         # Golden yellow
        
        # Fallback
        "Person": "#95A5A6",          # Gray
        "Unknown": "#7F8C8D",         # Dark gray
    }

    for r in records:
        for side in ["source", "target"]:
            node_id = r[f"{side}_id"]
            labels = r[f"{side}_labels"]
            props = r[f"{side}_props"]

            if node_id in nodes:
                continue

            # Get most specific label
            label = get_display_label(labels)
            
            # Apply filters if provided
            if entity_filters and label not in entity_filters:
                continue

            name = props.get("name", props.get("id", str(node_id)))
            
            # Get base color from role
            base_color = color_map.get(label, color_map["Unknown"])
            color = base_color
            size = 20  # Increased base size for better visibility
            
            # ENHANCED: Build detailed tooltip with proper plain text formatting
            title_lines = []
            
            # Check if this is the root node first
            is_root = (root_entity_id and props.get("id") == root_entity_id)
            
            if is_root:
                title_lines.append("🎯 ROOT NODE (Selected Entity)")
                title_lines.append("=" * 45)
            
            # Entity header
            title_lines.append(f"[{label.upper()}]")
            title_lines.append(f"{name}")
            title_lines.append(f"ID: {props.get('id', 'N/A')}")
            title_lines.append("-" * 45)
            
            # Add entity-specific attributes
            if label == "Claim":
                title_lines.append("CLAIM DETAILS:")
                if props.get('claim_amount'):
                    title_lines.append(f"  💰 Amount: ${props['claim_amount']:,.2f}")
                if props.get('claim_type'):
                    title_lines.append(f"  📋 Type: {props['claim_type']}")
                if props.get('claim_date'):
                    title_lines.append(f"  📅 Date: {props['claim_date'][:10]}")
                    
            elif label in ["Claimant", "Witness", "Adjuster"]:
                title_lines.append(f"{label.upper()} DETAILS:")
                if props.get('ssn'):
                    title_lines.append(f"  🔢 SSN: {props['ssn']}")
                if props.get('phone'):
                    title_lines.append(f"  📞 Phone: {props['phone']}")
                if props.get('employee_id'):
                    title_lines.append(f"  👤 Employee ID: {props['employee_id']}")
                    
            elif label == "MedicalProvider":
                title_lines.append("PROVIDER DETAILS:")
                if props.get('license'):
                    title_lines.append(f"  📜 License: {props['license']}")
                    
            elif label == "Attorney":
                title_lines.append("ATTORNEY DETAILS:")
                if props.get('bar_number'):
                    title_lines.append(f"  ⚖️  Bar Number: {props['bar_number']}")
                    
            elif label == "BodyShop":
                title_lines.append("BODY SHOP DETAILS:")
                if props.get('license'):
                    title_lines.append(f"  🔧 License: {props['license']}")

            # VISUAL HIERARCHY: Confirmed Fraud > Suspicious > Normal
            # Confirmed fraud takes precedence and uses RED
            if props.get("is_fraud"):
                color = "#E74C3C"  # Bright red - RESERVED for confirmed fraud
                size = 35
                title_lines.append("-" * 45)
                title_lines.append("🚨 CONFIRMED FRAUD")
                title_lines.append(f"  Fraud Type: {props.get('fraud_type', 'Unknown')}")

            # Suspicious entities use ORANGE spectrum (never red)
            elif props.get("suspicious"):
                suspicion_score = props.get('suspicion_score', 50)
                color = get_color_gradient(suspicion_score, base_color)
                size = 18 + (suspicion_score / 6)  # Size 18-35 (smaller than fraud)
                title_lines.append("-" * 45)
                title_lines.append("⚠️ SUSPICIOUS - Requires Investigation")
                title_lines.append(f"  Pattern: {props.get('suspicion_type', 'Unknown')}")
                title_lines.append(f"  Risk Score: {suspicion_score}/100")
                title_lines.append("  Status: Unconfirmed - Qualified Lead")
            
            # Highlight root node (but don't override fraud colors)
            if is_root:
                size = max(size, 40)  # Make root significantly larger
            
            # Join all tooltip lines with newlines for proper plain text display
            title = "\n".join(title_lines)

            nodes[node_id] = Node(
                id=str(node_id),
                label=name[:25] + "..." if len(name) > 25 else name,
                size=size,
                color=color,
                title=title,
                # Enhanced node properties
                shape="star" if is_root else "dot",
                font={"size": 14, "color": "#FFFFFF", "face": "Arial"},
                # ENHANCED: Special visual effects for fraud nodes
                borderWidth=5 if props.get("is_fraud") else (3 if props.get("suspicious") else 1),
                borderWidthSelected=7,
                # Add shadow effect for fraud nodes (pulsating effect substitute)
                shadow={"enabled": True, "size": 15, "x": 0, "y": 0} if props.get("is_fraud") else (
                    {"enabled": True, "size": 10, "x": 0, "y": 0} if props.get("suspicious") else False
                ),
                # Shiny effect for fraud nodes
                shapeProperties={
                    "borderDashes": False,
                    "borderRadius": 0,
                    "interpolation": True,
                    "useImageSize": False,
                    "useBorderWithImage": False
                }
            )

        # Add edge with better styling
        if r["source_id"] in nodes and r["target_id"] in nodes:
            edges.append(
                Edge(
                    source=str(r["source_id"]),
                    target=str(r["target_id"]),
                    label=r["rel_type"],
                    type="CURVE_SMOOTH",
                    color={"color": "#95A5A6", "highlight": "#3498DB", "hover": "#3498DB"},
                    width=2,
                    smooth={"enabled": True, "type": "continuous"}
                )
            )

    return list(nodes.values()), edges


def create_enhanced_graph_config(width=1400, height=800):
    """
    ENHANCED: Create graph configuration with physics disabled after layout for stable dragging
    """
    return Config(
        width=width,
        height=height,
        directed=False,
        physics={
            "enabled": True,                         # Enabled initially for layout
            "stabilization": {
                "enabled": True,
                "iterations": 500,
                "fit": True,
                "onlyDynamicEdges": False
            },
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -100,
                "centralGravity": 0.01,
                "springLength": 250,
                "springConstant": 0.05,
                "damping": 0.95,
                "avoidOverlap": 1.0
            },
            "adaptiveTimestep": True,
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.3,
                "springLength": 200,
                "springConstant": 0.04,
                "damping": 0.95,
                "avoidOverlap": 1.0
            }
        },
        hierarchical=False,
        interaction={
            "hover": True,
            "tooltipDelay": 100,
            "zoomView": True,
            "dragView": True,
            "dragNodes": True,
            "navigationButtons": True,
            "keyboard": True,
            "multiselect": False,
            "selectable": True,
            "hideEdgesOnDrag": False,
            "hideNodesOnDrag": False
        },
        layout={
            "randomSeed": 42,
            "improvedLayout": True
        },
        edges={
            "smooth": {
                "enabled": True,
                "type": "continuous",
                "roundness": 0.5
            }
        },
        nodes={
            "borderWidth": 2,
            "borderWidthSelected": 4,
            "font": {
                "size": 14,
                "face": "Arial"
            },
            "fixed": False,
            "physics": True
        },
        configure={
            "enabled": False
        }
    )

@st.dialog("Suspicious Network Visualization", width="large")
def show_network_dialog(nodes, edges, entity_name, fraud_type):
    """Display network visualization in a modal overlay"""
    st.markdown(f"### 🌐 {entity_name}")
    st.caption(f"Fraud Type: {fraud_type}")
    
    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Nodes", len(nodes))
    with col2:
        st.metric("Relationships", len(edges))
    with col3:
        fraud_count = sum(1 for n in nodes if 'FRAUD' in n.title)
        st.metric("Confirmed Fraud", fraud_count)
    with col4:
        suspicious_count = sum(1 for n in nodes if 'SUSPICIOUS' in n.title)
        st.metric("Suspicious", suspicious_count)
    
    config = create_enhanced_graph_config(width=1000, height=600)
    agraph(nodes, edges, config)


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.title("🔍 Fraud Detection System")
page = st.sidebar.radio(
    "Navigation",
    ["Network Discovery", "Fraud Ring Visualization", "New Claim", "Admin Panel"]
)

# -----------------------------------------------------------------------------
# Page 1: ENHANCED Network Discovery
# -----------------------------------------------------------------------------
if page == "Network Discovery":
    st.title("🌐 Network Discovery")
    st.markdown("Explore entity neighborhoods and relationships in the insurance network")
    st.info("💡 The visualization shows a **connected network** starting from the selected entity (⭐ star shape) and expanding outward through relationships.")

    entity_types = get_entity_types(driver)

    if not entity_types:
        st.warning("⚠️ No data found in database. Please use Admin Panel to generate data.")
        st.stop()

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        selected_type = st.selectbox("Entity Type", entity_types)
    with col2:
        entities = get_entities_by_type(driver, selected_type)
        if not entities:
            st.warning(f"No entities of type {selected_type} found")
            st.stop()
        selected_entity = st.selectbox(
            "Entity",
            entities,
            format_func=lambda x: f"{x[1]} ({x[0]})"
        )
    with col3:
        hops = st.number_input("Hops", 1, 5, 2)

    st.markdown("### Entity Filters")
    st.caption("Select which entity types to include in the network visualization")
    
    # Filter out generic "Person" label - we have specific person types (Claimant, Witness, Adjuster)
    filtered_entity_types = [et for et in entity_types if et != "Person"]
    
    cols = st.columns(4)
    filters = {}
    for i, et in enumerate(filtered_entity_types):
        with cols[i % 4]:
            # Disable checkbox for selected entity type (root cannot be filtered out)
            is_root_entity = (et == selected_type)
            if is_root_entity:
                filters[et] = st.checkbox(et, True, disabled=True, key=f"filter_nd_{et}",
                                         help="🎯 Root entity - cannot be filtered out")
            else:
                filters[et] = st.checkbox(et, True, key=f"filter_nd_{et}")

    active_filters = [k for k, v in filters.items() if v]

    if st.button("🔍 Explore Network", type="primary"):
        # ENHANCED: Track performance
        timer = PerformanceTimer()
        timer.start()
        
        with st.spinner("Loading neighborhood..."):
            records = get_neighborhood(
                driver,
                selected_type,
                selected_entity[0],
                hops,
                active_filters
            )

            if records:
                nodes, edges = create_graph_visualization(
                    records, 
                    active_filters,
                    root_entity_id=selected_entity[0]
                )
                
                # Stop timer and set counts
                timer.stop()
                timer.set_counts(len(nodes), len(edges))
                
                # STORE IN SESSION STATE to persist across interactions
                st.session_state.nd_nodes = nodes
                st.session_state.nd_edges = edges
                st.session_state.nd_timer = timer
                st.session_state.nd_entity_name = selected_entity[1]
            else:
                st.session_state.nd_nodes = None
                st.warning("No relationships found for this entity with current filters.")
                st.info("💡 Try increasing the number of hops or enabling more entity type filters.")

    # RENDER GRAPH FROM SESSION STATE (outside the button block)
    if st.session_state.get('nd_nodes'):
        nodes = st.session_state.nd_nodes
        edges = st.session_state.nd_edges
        timer = st.session_state.nd_timer
        entity_name = st.session_state.nd_entity_name
        
        st.markdown(f"### Network for **{entity_name}** (⭐ Root Node)")
        
        # Performance metrics
        display_performance_metrics(timer, f"{hops}-Hop Network Traversal")
        
        # Statistics
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            fraud_nodes = sum(1 for n in nodes if 'FRAUD' in n.title)
            st.metric("🔴 Confirmed Fraud", fraud_nodes)
        with col_stat2:
            suspicious_nodes = sum(1 for n in nodes if 'SUSPICIOUS' in n.title)
            st.metric("🟠 Suspicious Detected", suspicious_nodes)
        with col_stat3:
            clean_nodes = len(nodes) - fraud_nodes - suspicious_nodes
            st.metric("✅ Clean Entities", clean_nodes)
        
        st.markdown("---")
        
        col_graph_title, col_rerender = st.columns([5, 1])
        with col_graph_title:
            st.markdown("#### 🎨 Interactive Network Graph")
            st.caption("💡 **Controls**: Mouse wheel to zoom • Drag background to pan • Drag nodes to reposition • Hover for details")
        with col_rerender:
            if st.button("🔄 Re-render", help="If graph disappears, click to re-render", key="nd_rerender"):
                st.rerun()
        
        config = create_enhanced_graph_config()
        agraph(nodes, edges, config)

# -----------------------------------------------------------------------------
# Page 2: ENHANCED Fraud Ring Visualization
# -----------------------------------------------------------------------------
elif page == "Fraud Ring Visualization":
    st.title("🚨 Fraud Ring Visualization")
    st.markdown("Analyze known fraud patterns and detect suspicious communities")

    tab1, tab2 = st.tabs(["Known Fraud Rings", "Fraud Detection"])

    with tab1:
        st.markdown("### Known Fraud Rings (Labeled Data)")
        st.info("These are explicitly labeled fraud patterns injected during data generation. Select a specific ring for detailed investigation.")

        # Step 1: Select fraud type
        fraud_types = ["Medical Mill", "Body Shop Kickback", "Staged Accident", "Phantom Passenger"]
        selected_fraud = st.selectbox("🎯 Step 1: Select Fraud Type", fraud_types)

        # Step 2: Get individual rings for selected type
        if selected_fraud:
            rings = get_individual_fraud_rings(driver, selected_fraud)
            
            if rings:
                st.markdown(f"### 📊 Individual {selected_fraud} Rings")
                
                # Display rings in a table for selection
                ring_options = []
                for i, ring in enumerate(rings):
                    ring_label = f"Ring #{i+1}: {ring['claim_name']} | ${ring['amount']:,.2f} | {ring['ring_size']} connected entities"
                    ring_options.append((ring_label, ring['claim_id']))
                
                selected_ring = st.selectbox(
                    "🔍 Step 2: Select Specific Ring to Investigate",
                    ring_options,
                    format_func=lambda x: x[0]
                )
                
                # Step 3: Hop control
                col_hop, col_viz = st.columns([1, 3])
                with col_hop:
                    hops = st.slider("🎚️ Neighborhood Hops", 1, 4, 2, 
                                    help="Control how far to expand from the fraud ring")
                
                if st.button("🔍 Visualize Selected Ring", type="primary"):
                    # ENHANCED: Track performance
                    timer = PerformanceTimer()
                    timer.start()
                    
                    with st.spinner(f"Loading fraud ring neighborhood ({hops} hops)..."):
                        # Get the selected ring's neighborhood
                        records = get_fraud_ring_neighborhood(driver, selected_ring[1], hops)

                        if records:
                            entity_types = get_entity_types(driver)
                            nodes, edges = create_graph_visualization(
                                records, 
                                entity_types,
                                root_entity_id=selected_ring[1]
                            )

                            # Stop timer
                            timer.stop()
                            timer.set_counts(len(nodes), len(edges))

                            st.markdown(f"### 🚨 Fraud Ring: **{selected_ring[0].split(':')[1].split('|')[0].strip()}**")
                            
                            # Show ring statistics
                            col_stat1, col_stat2, col_stat3 = st.columns(3)
                            with col_stat1:
                                fraud_nodes = sum(1 for n in nodes if 'FRAUD' in n.title)
                                st.metric("🔴 Fraud Entities", fraud_nodes)
                            with col_stat2:
                                st.metric("🔗 Total Entities", len(nodes))
                            with col_stat3:
                                st.metric("📊 Relationships", len(edges))
                            
                            # ENHANCED: Performance display
                            display_performance_metrics(timer, f"{selected_fraud} Ring Analysis")

                            st.markdown("---")
                            
                            # Add re-render button
                            col_fraud_title, col_fraud_rerender = st.columns([5, 1])
                            with col_fraud_title:
                                st.markdown("#### 🎨 Fraud Ring Network")
                                st.caption(f"⭐ Root claim shown with star shape • {hops}-hop neighborhood • Red nodes are confirmed fraud")
                            with col_fraud_rerender:
                                if st.button("🔄 Re-render", help="If graph disappears, click to re-render", key="fraud_rerender"):
                                    st.rerun()
                            
                            st.info("⚠️ **Tip**: Wait for nodes to stop moving before dragging. If graph disappears, click Re-render button.")
                            
                            config = create_enhanced_graph_config()
                            agraph(nodes, edges, config)
                            
                            # Ring insights
                            with st.expander("🔍 Ring Pattern Analysis"):
                                st.markdown("#### Fraud Ring Characteristics")
                                
                                # Analyze the pattern
                                entity_breakdown = {}
                                for node in nodes:
                                    if 'FRAUD' in node.title:
                                        node_type = node.title.split('[')[1].split(']')[0] if '[' in node.title else 'Unknown'
                                        entity_breakdown[node_type] = entity_breakdown.get(node_type, 0) + 1
                                
                                if entity_breakdown:
                                    st.markdown("**Fraudulent Entities by Type:**")
                                    for entity_type, count in sorted(entity_breakdown.items(), key=lambda x: x[1], reverse=True):
                                        st.markdown(f"- **{entity_type}**: {count} entities")
                                
                                st.markdown(f"""
                                **Pattern Indicators:**
                                - **Fraud Type**: {selected_fraud}
                                - **Network Density**: {len(edges) / max(len(nodes), 1):.2f} connections per entity
                                - **Ring Size**: {len([n for n in nodes if 'FRAUD' in n.title])} confirmed fraud entities
                                """)
                        else:
                            st.warning("No relationships found for this fraud ring.")
            else:
                st.warning(f"No {selected_fraud} rings found in database. Generate data in Admin Panel.")

    with tab2:
        st.markdown("### Fraud Detection Algorithms")
        st.markdown("Run advanced algorithms to detect **unlabeled** suspicious patterns")
        
        # Detection Parameters
        with st.expander("⚙️ Detection Parameters", expanded=False):
            st.caption("Adjust sensitivity thresholds for each detection algorithm")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                min_claims = st.number_input(
                    "Medical Mill", 3, 20, 5,
                    help="Min claims at a provider"
                )
            with col2:
                min_shared = st.number_input(
                    "Kickback", 2, 10, 3,
                    help="Min shared claims (attorney-bodyshop)"
                )
            with col3:
                min_staged = st.number_input(
                    "Staged Accident", 2, 10, 2,
                    help="Min shared claims between people"
                )
            with col4:
                min_phantom = st.number_input(
                    "Phantom Passenger", 2, 10, 3,
                    help="Min KNOWS connections"
                )
            
            min_adjuster = st.number_input(
                "Adjuster Collusion", 2, 10, 4,
                help="Min shared claims between adjuster-provider pair"
            )
        
        # Run Detection Button
        col_left, col_center, col_right = st.columns([2, 2, 2])
        with col_center:
            run_detection = st.button("🚨 Run Fraud Detection", type="primary", use_container_width=True)
        
        if run_detection:
            timer = PerformanceTimer()
            timer.start()
            
            with st.spinner("Running fraud detection algorithms..."):
                old_stdout = sys.stdout
                sys.stdout = buffer = io.StringIO()
                
                try:
                    detector = FraudDetector()
                    results = detector.run_all_detections(
                        min_claims=min_claims,
                        min_shared_claims=min_shared,
                        min_staged_claims=min_staged,
                        min_connections=min_phantom,
                        min_adjuster_collusion=min_adjuster
                    )
                    detector.close()
                    
                    output = buffer.getvalue()
                    sys.stdout = old_stdout
                    timer.stop()
                    
                    # Store in session state
                    st.session_state.fd_results = results
                    st.session_state.fd_log = output
                    st.session_state.fd_time = timer.get_duration()
                    
                    # Fetch flagged entities
                    with driver.session() as session:
                        flagged = session.run("""
                            MATCH (n)
                            WHERE n.suspicious = true
                            RETURN n.id as id,
                                   labels(n) as labels,
                                   n.name as name,
                                   n.suspicion_type as fraud_type,
                                   n.suspicion_score as score
                            ORDER BY n.suspicion_score DESC
                        """).data()
                    
                    st.session_state.fd_flagged = flagged
                    st.session_state.fd_complete = True
                    
                except Exception as e:
                    sys.stdout = old_stdout
                    st.error(f"Error during fraud detection: {str(e)}")
                    st.session_state.fd_complete = False
        
        # Display Results
        if st.session_state.get('fd_complete'):
            results = st.session_state.fd_results
            flagged = st.session_state.fd_flagged
            
            st.success(f"✅ Detection completed in {st.session_state.fd_time} ms")
            
            # Summary Cards
            st.markdown("#### 📊 Detection Summary")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("🏥 Medical Mills", len(results['medical_mills']))
            with col2:
                st.metric("🔧 Kickbacks", len(results['kickbacks']))
            with col3:
                st.metric("🚗 Staged Accidents", len(results['staged_accidents']))
            with col4:
                st.metric("👻 Phantom Passengers", len(results['phantom_passengers']))
            with col5:
                st.metric("👔 Adjuster Collusion", len(results['adjuster_collusion']))
            
            st.markdown("---")
            
            # Two-column layout
            col_findings, col_viz = st.columns([3, 2])
            
            with col_findings:
                st.markdown("#### 🔍 Detailed Findings")
                
                finding_tabs = st.tabs(["🏥 Mills", "🔧 Kickbacks", "🚗 Staged", "👻 Phantom", "👔 Adjuster"])
                
                with finding_tabs[0]:
                    if results['medical_mills']:
                        for mill in results['medical_mills']:
                            st.markdown(
                                f"**{mill['provider_name']}**  \n"
                                f"Claims: {mill['claim_count']} • Avg: ${mill['avg_amount']:,.0f} • Score: {mill['suspicion_score']}"
                            )
                            st.divider()
                    else:
                        st.info("No medical mills detected")
                
                with finding_tabs[1]:
                    if results['kickbacks']:
                        for kb in results['kickbacks']:
                            st.markdown(
                                f"**{kb['attorney_name']}** → **{kb['bodyshop_name']}**  \n"
                                f"Shared Claims: {kb['shared_claims']} • Score: {kb['suspicion_score']}"
                            )
                            st.divider()
                    else:
                        st.info("No kickback schemes detected")
                
                with finding_tabs[2]:
                    if results['staged_accidents']:
                        for acc in results['staged_accidents']:
                            st.markdown(
                                f"**{acc['person1_id']}** & **{acc['person2_id']}**  \n"
                                f"Shared Claims: {acc['shared_claims']} • Score: {acc['suspicion_score']}"
                            )
                            st.divider()
                    else:
                        st.info("No staged accidents detected")
                
                with finding_tabs[3]:
                    if results['phantom_passengers']:
                        for phantom in results['phantom_passengers']:
                            st.markdown(
                                f"**{phantom['person_name']}**  \n"
                                f"Claims: {phantom['claim_count']} • Links: {phantom['connection_count']} • Score: {phantom['suspicion_score']}"
                            )
                            st.divider()
                    else:
                        st.info("No phantom passengers detected")

                with finding_tabs[4]:
                    if results['adjuster_collusion']:
                        for col in results['adjuster_collusion']:
                            st.markdown(
                                f"**{col['adjuster_name']}** ↔ **{col['provider_name']}**  \n"
                                f"Shared Claims: {col['shared_claims']} • Score: {col['suspicion_score']}"
                            )
                            st.divider()
                    else:
                        st.info("No adjuster-provider collusion detected")
            
            with col_viz:
                st.markdown("#### 🎨 Visualize Network")
                
                if flagged:
                    # Group by fraud type
                    flagged_by_type = {}
                    for entity in flagged:
                        ftype = entity['fraud_type']
                        if ftype not in flagged_by_type:
                            flagged_by_type[ftype] = []
                        flagged_by_type[ftype].append(entity)
                    
                    selected_type = st.selectbox(
                        "Fraud Type",
                        list(flagged_by_type.keys()),
                        key="fd_type_select"
                    )
                    
                    if selected_type:
                        entity_options = [
                            (f"{e['name']} (Score: {e['score']})", e['id'], e['labels'])
                            for e in flagged_by_type[selected_type]
                        ]
                        selected_entity = st.selectbox(
                            "Entity",
                            entity_options,
                            format_func=lambda x: x[0],
                            key="fd_entity_select"
                        )
                    
                    viz_hops = st.slider("Network Depth", 1, 3, 2, key="fd_hops_slider")
                    
                    if st.button("🔍 Visualize Network", type="primary", use_container_width=True, key="fd_viz_button"):
                        if selected_entity:
                            entity_type = selected_entity[2][0] if selected_entity[2] else 'Person'
                            
                            records = get_neighborhood(
                                driver,
                                entity_type,
                                selected_entity[1],
                                viz_hops,
                                get_entity_types(driver)
                            )
                            
                            if records:
                                nodes, edges = create_graph_visualization(
                                    records,
                                    get_entity_types(driver),
                                    root_entity_id=selected_entity[1]
                                )
                                
                                entity_name = selected_entity[0].split(" (")[0]
                                show_network_dialog(nodes, edges, entity_name, selected_type)
                            else:
                                st.warning("No relationships found for this entity")
                else:
                    st.info("No suspicious entities to visualize")
            
            # Technical Log
            with st.expander("📋 Technical Detection Log"):
                st.code(st.session_state.fd_log, language="text")


# -----------------------------------------------------------------------------
# Page 3: New Claim (Unchanged for now - keeping existing functionality)
# -----------------------------------------------------------------------------
elif page == "New Claim":
    st.title("📝 New Auto Insurance Claim")
    st.markdown("Submit a new claim and analyze fraud risk based on connected entities")
    
    # Initialize session state for risk assessment
    if 'claim_risk_assessment' not in st.session_state:
        st.session_state.claim_risk_assessment = None
    if 'claim_submitted' not in st.session_state:
        st.session_state.claim_submitted = False
    if 'new_claim_id' not in st.session_state:
        st.session_state.new_claim_id = None

    # Auto-generate claim ID
    claim_id = f"CLM_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Fetch entity pools for dropdowns
    adjuster_pool = get_adjuster_pool(driver)
    medical_providers = get_medical_providers(driver)
    body_shops = get_body_shops(driver)
    attorneys = get_attorneys(driver)
    existing_claimants = get_existing_claimants(driver)
    existing_witnesses = get_existing_witnesses(driver)
    
    # Check if pools are populated
    if not adjuster_pool:
        st.warning("⚠️ No adjusters found in database. Please generate data in Admin Panel first.")
        st.stop()

    # =========================================================================
    # SECTION 1: Incident Details
    # =========================================================================
    st.markdown("### 🚗 Section 1: Incident Details")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        claim_amount = st.number_input(
            "Claim Amount ($)",
            min_value=500.0,
            max_value=100000.0,
            value=12000.0,
            step=500.0,
            help="Total claim value"
        )
    
    with col2:
        incident_date = st.date_input(
            "Incident Date",
            value=datetime.now() - timedelta(days=random.randint(1, 30)),
            max_value=datetime.now(),
            help="Date of the accident"
        )
    
    with col3:
        incident_types = [
            "Rear-End Collision",
            "Side Impact",
            "Multi-Vehicle Accident", 
            "Single Vehicle Accident",
            "Hit and Run",
            "Parking Lot Incident"
        ]
        incident_type = st.selectbox(
            "Incident Type",
            incident_types,
            help="Type of auto incident"
        )
    
    # Claim description
    claim_description = st.text_input(
        "Brief Description",
        value=f"{incident_type} - {incident_date.strftime('%B %d, %Y')}",
        help="Short description for the claim"
    )

    st.markdown("---")

    # =========================================================================
    # SECTION 2: Involved Parties
    # =========================================================================
    st.markdown("### 👥 Section 2: Involved Parties")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        # ----- CLAIMANT -----
        st.markdown("#### 👤 Claimant (Required)")
        claimant_type = st.radio(
            "Claimant Selection",
            ["New Claimant", "Existing Claimant"],
            horizontal=True,
            key="claimant_type",
            help="Create new or link to existing person"
        )
        
        selected_claimant_id = None
        new_claimant_name = None
        
        if claimant_type == "New Claimant":
            new_claimant_name = st.text_input(
                "Claimant Name",
                placeholder="Enter full name",
                key="new_claimant_name"
            )
        else:
            if existing_claimants:
                selected_claimant = st.selectbox(
                    "Select Existing Claimant",
                    existing_claimants,
                    format_func=lambda x: x[1],
                    key="existing_claimant"
                )
                selected_claimant_id = selected_claimant[0] if selected_claimant else None
            else:
                st.info("No existing claimants found. Please create a new one.")
                claimant_type = "New Claimant"
                new_claimant_name = st.text_input(
                    "Claimant Name",
                    placeholder="Enter full name",
                    key="new_claimant_name_fallback"
                )
        
        # ----- WITNESS -----
        st.markdown("#### 👁️ Witness (Optional)")
        witness_type = st.radio(
            "Witness Selection",
            ["No Witness", "New Witness", "Existing Witness"],
            horizontal=True,
            key="witness_type"
        )
        
        selected_witness_id = None
        new_witness_name = None
        
        if witness_type == "New Witness":
            new_witness_name = st.text_input(
                "Witness Name",
                placeholder="Enter full name",
                key="new_witness_name"
            )
        elif witness_type == "Existing Witness":
            if existing_witnesses:
                selected_witness = st.selectbox(
                    "Select Existing Witness",
                    existing_witnesses,
                    format_func=lambda x: x[1],
                    key="existing_witness"
                )
                selected_witness_id = selected_witness[0] if selected_witness else None
            else:
                st.info("No existing witnesses found.")
    
    with col_right:
        # ----- ADJUSTER -----
        st.markdown("#### 👔 Claims Adjuster (Required)")
        st.caption("Assigned from company adjuster pool")
        
        selected_adjuster = st.selectbox(
            "Assign Adjuster",
            adjuster_pool,
            format_func=lambda x: x[1],
            key="adjuster_select",
            help="Select adjuster to handle this claim"
        )
        selected_adjuster_id = selected_adjuster[0] if selected_adjuster else None
        
        # Show warning if adjuster is flagged
        if selected_adjuster and ('🔴' in selected_adjuster[1] or '🟠' in selected_adjuster[1]):
            st.warning("⚠️ Selected adjuster has fraud/suspicion flags!")

    st.markdown("---")

    # =========================================================================
    # SECTION 3: Service Providers (Optional)
    # =========================================================================
    st.markdown("### 🏢 Section 3: Service Providers (Optional)")
    st.caption("Link claim to existing service providers to test fraud proximity detection")
    
    col_med, col_body, col_att = st.columns(3)
    
    with col_med:
        st.markdown("#### 🏥 Medical Provider")
        use_medical = st.checkbox("Include Medical Provider", key="use_medical")
        selected_medical_id = None
        
        if use_medical:
            if medical_providers:
                selected_medical = st.selectbox(
                    "Select Provider",
                    medical_providers,
                    format_func=lambda x: x[1],
                    key="medical_select"
                )
                selected_medical_id = selected_medical[0] if selected_medical else None
                
                if selected_medical and '🔴' in selected_medical[1]:
                    st.error("⚠️ CONFIRMED FRAUD provider!")
                elif selected_medical and '🟠' in selected_medical[1]:
                    st.warning("⚠️ Suspicious provider!")
            else:
                st.info("No medical providers in database")
    
    with col_body:
        st.markdown("#### 🔧 Body Shop")
        use_bodyshop = st.checkbox("Include Body Shop", key="use_bodyshop")
        selected_bodyshop_id = None
        
        if use_bodyshop:
            if body_shops:
                selected_bodyshop = st.selectbox(
                    "Select Body Shop",
                    body_shops,
                    format_func=lambda x: x[1],
                    key="bodyshop_select"
                )
                selected_bodyshop_id = selected_bodyshop[0] if selected_bodyshop else None
                
                if selected_bodyshop and '🔴' in selected_bodyshop[1]:
                    st.error("⚠️ CONFIRMED FRAUD body shop!")
                elif selected_bodyshop and '🟠' in selected_bodyshop[1]:
                    st.warning("⚠️ Suspicious body shop!")
            else:
                st.info("No body shops in database")
    
    with col_att:
        st.markdown("#### ⚖️ Attorney")
        use_attorney = st.checkbox("Include Attorney", key="use_attorney")
        selected_attorney_id = None
        
        if use_attorney:
            if attorneys:
                selected_attorney = st.selectbox(
                    "Select Attorney",
                    attorneys,
                    format_func=lambda x: x[1],
                    key="attorney_select"
                )
                selected_attorney_id = selected_attorney[0] if selected_attorney else None
                
                if selected_attorney and '🔴' in selected_attorney[1]:
                    st.error("⚠️ CONFIRMED FRAUD attorney!")
                elif selected_attorney and '🟠' in selected_attorney[1]:
                    st.warning("⚠️ Suspicious attorney!")
            else:
                st.info("No attorneys in database")

    st.markdown("---")

    # =========================================================================
    # SECTION 4: Live Risk Assessment
    # =========================================================================
    st.markdown("### ⚠️ Risk Assessment Preview")
    
    # Build entity map for risk assessment
    entities_to_check = {}
    
    if claimant_type == "Existing Claimant" and selected_claimant_id:
        entities_to_check['Claimant'] = selected_claimant_id
    if witness_type == "Existing Witness" and selected_witness_id:
        entities_to_check['Witness'] = selected_witness_id
    if selected_adjuster_id:
        entities_to_check['Adjuster'] = selected_adjuster_id
    if use_medical and selected_medical_id:
        entities_to_check['MedicalProvider'] = selected_medical_id
    if use_bodyshop and selected_bodyshop_id:
        entities_to_check['BodyShop'] = selected_bodyshop_id
    if use_attorney and selected_attorney_id:
        entities_to_check['Attorney'] = selected_attorney_id
    
    # Perform risk assessment
    if entities_to_check:
        risk = assess_entity_risk(driver, entities_to_check)
        
        # Display risk score with color coding
        col_score, col_fraud, col_suspicious = st.columns(3)
        
        with col_score:
            if risk['score'] >= 70:
                st.error(f"🚨 Risk Score: {risk['score']}/100 - **HIGH RISK**")
            elif risk['score'] >= 40:
                st.warning(f"⚠️ Risk Score: {risk['score']}/100 - **MEDIUM RISK**")
            elif risk['score'] > 0:
                st.info(f"📊 Risk Score: {risk['score']}/100 - **LOW RISK**")
            else:
                st.success(f"✅ Risk Score: {risk['score']}/100 - **CLEAN**")
        
        with col_fraud:
            st.metric("🔴 Confirmed Fraud", risk['fraud_count'], 
                     help="Entities in 2-hop neighborhood with confirmed fraud")
        
        with col_suspicious:
            st.metric("🟠 Suspicious", risk['suspicious_count'],
                     help="Entities in 2-hop neighborhood flagged as suspicious")
        
        # Show detailed warnings
        if risk['warnings']:
            with st.expander("📋 Detailed Risk Findings", expanded=True):
                for warning in risk['warnings']:
                    st.markdown(f"- {warning}")
                
                # Show connected fraud entities
                if risk['fraud_entities']:
                    st.markdown("**Connected Fraud Entities:**")
                    for entity in risk['fraud_entities']:
                        connection = f" (via {entity.get('connection', 'direct')})" if 'connection' in entity else ""
                        st.markdown(f"  - 🔴 {entity['type']}: {entity['name']} - {entity.get('fraud_type', 'Unknown')}{connection}")
                
                # Show connected suspicious entities
                if risk['suspicious_entities']:
                    st.markdown("**Connected Suspicious Entities:**")
                    for entity in risk['suspicious_entities']:
                        connection = f" (via {entity.get('connection', 'direct')})" if 'connection' in entity else ""
                        st.markdown(f"  - 🟠 {entity['type']}: {entity['name']} - {entity.get('suspicion_type', 'Unknown')}{connection}")
    else:
        st.info("💡 Select existing entities above to preview fraud risk assessment")

    st.markdown("---")

    # =========================================================================
    # SECTION 5: Submit Claim
    # =========================================================================
    col_submit, col_preview = st.columns([2, 1])
    
    with col_submit:
        # Validate before showing submit button
        can_submit = True
        validation_errors = []
        
        if claimant_type == "New Claimant" and not new_claimant_name:
            can_submit = False
            validation_errors.append("Claimant name is required")
        
        if not selected_adjuster_id:
            can_submit = False
            validation_errors.append("Adjuster must be assigned")
        
        if validation_errors:
            for error in validation_errors:
                st.error(f"❌ {error}")
        
        submit_button = st.button(
            "✅ Submit Claim",
            type="primary",
            disabled=not can_submit,
            use_container_width=True
        )
    
    with col_preview:
        preview_button = st.button(
            "🔍 Preview Network",
            type="secondary",
            use_container_width=True,
            help="Preview the claim's network before submitting"
        )

    # Handle submission
    if submit_button and can_submit:
        try:
            with driver.session() as session:
                # Generate IDs for new entities
                person_counter = int(datetime.now().strftime('%H%M%S'))
                
                # Determine claimant ID
                if claimant_type == "New Claimant":
                    claimant_id = f"P_{person_counter:05d}"
                    claimant_name = new_claimant_name
                else:
                    claimant_id = selected_claimant_id
                    claimant_name = None  # Will use existing
                
                # Build the Cypher query dynamically
                query_parts = []
                params = {
                    'claim_id': claim_id,
                    'claim_name': claim_description,
                    'claim_amount': claim_amount,
                    'claim_date': incident_date.isoformat(),
                    'incident_type': incident_type,
                    'adjuster_id': selected_adjuster_id
                }
                
                # Create claim and link to adjuster
                query_parts.append("""
                    MATCH (adj:Person:Adjuster {id: $adjuster_id})
                    CREATE (c:Claim {
                        id: $claim_id,
                        name: $claim_name,
                        claim_amount: $claim_amount,
                        claim_date: $claim_date,
                        claim_type: 'Auto',
                        incident_type: $incident_type,
                        is_fraud: false
                    })
                    CREATE (c)-[:HANDLED_BY]->(adj)
                """)
                
                # Handle claimant
                if claimant_type == "New Claimant":
                    query_parts.append("""
                        CREATE (claimant:Person:Claimant {
                            id: $claimant_id,
                            name: $claimant_name,
                            ssn: $claimant_ssn,
                            phone: $claimant_phone
                        })
                        CREATE (c)-[:FILED_BY]->(claimant)
                    """)
                    params['claimant_id'] = claimant_id
                    params['claimant_name'] = claimant_name
                    params['claimant_ssn'] = f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"
                    params['claimant_phone'] = f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
                else:
                    query_parts.append("""
                        WITH c, adj
                        MATCH (claimant:Person {id: $claimant_id})
                        CREATE (c)-[:FILED_BY]->(claimant)
                    """)
                    params['claimant_id'] = claimant_id
                
                # Handle witness
                if witness_type == "New Witness" and new_witness_name:
                    witness_id = f"P_{person_counter + 1:05d}"
                    query_parts.append("""
                        CREATE (witness:Person:Witness {
                            id: $witness_id,
                            name: $witness_name,
                            phone: $witness_phone
                        })
                        CREATE (c)-[:WITNESSED_BY]->(witness)
                    """)
                    params['witness_id'] = witness_id
                    params['witness_name'] = new_witness_name
                    params['witness_phone'] = f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
                elif witness_type == "Existing Witness" and selected_witness_id:
                    query_parts.append("""
                        WITH c
                        MATCH (witness:Person {id: $witness_id})
                        CREATE (c)-[:WITNESSED_BY]->(witness)
                    """)
                    params['witness_id'] = selected_witness_id
                
                # Handle service providers
                if use_medical and selected_medical_id:
                    query_parts.append("""
                        WITH c
                        MATCH (med:MedicalProvider {id: $medical_id})
                        CREATE (c)-[:TREATED_AT]->(med)
                    """)
                    params['medical_id'] = selected_medical_id
                
                if use_bodyshop and selected_bodyshop_id:
                    query_parts.append("""
                        WITH c
                        MATCH (body:BodyShop {id: $bodyshop_id})
                        CREATE (c)-[:REPAIRED_AT]->(body)
                    """)
                    params['bodyshop_id'] = selected_bodyshop_id
                
                if use_attorney and selected_attorney_id:
                    query_parts.append("""
                        WITH c
                        MATCH (att:Attorney {id: $attorney_id})
                        CREATE (c)-[:REPRESENTED_BY]->(att)
                    """)
                    params['attorney_id'] = selected_attorney_id
                
                # Execute the combined query
                full_query = "\n".join(query_parts)
                session.run(full_query, **params)
            
            st.session_state.claim_submitted = True
            st.session_state.new_claim_id = claim_id
            st.success(f"✅ Claim **{claim_id}** submitted successfully!")
            
            # Automatically show network analysis
            st.markdown("---")
            st.markdown("### 🌐 Claim Network Analysis")
            
        except Exception as e:
            st.error(f"❌ Error creating claim: {str(e)}")
            st.session_state.claim_submitted = False

    # Show network visualization after submission or on preview
    if st.session_state.claim_submitted or preview_button:
        viz_claim_id = st.session_state.new_claim_id if st.session_state.claim_submitted else None
        
        if st.session_state.claim_submitted and viz_claim_id:
            st.markdown("#### Network Visualization")
            
            # Performance tracking
            timer = PerformanceTimer()
            timer.start()
            
            with st.spinner("Analyzing claim network..."):
                entity_types = get_entity_types(driver)
                records = get_neighborhood(driver, "Claim", viz_claim_id, 2, entity_types)
                
                if records:
                    nodes, edges = create_graph_visualization(
                        records,
                        entity_types,
                        root_entity_id=viz_claim_id
                    )
                    
                    timer.stop()
                    timer.set_counts(len(nodes), len(edges))
                    
                    # Statistics
                    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                    with col_stat1:
                        st.metric("🔗 Connected Entities", len(nodes))
                    with col_stat2:
                        st.metric("📊 Relationships", len(edges))
                    with col_stat3:
                        fraud_nodes = sum(1 for n in nodes if 'CONFIRMED FRAUD' in n.title)
                        st.metric("🔴 Fraud in Network", fraud_nodes)
                    with col_stat4:
                        suspicious_nodes = sum(1 for n in nodes if 'SUSPICIOUS' in n.title)
                        st.metric("🟠 Suspicious", suspicious_nodes)
                    
                    # Risk assessment banner
                    if fraud_nodes > 0:
                        st.error(f"🚨 **HIGH RISK**: This claim is connected to {fraud_nodes} confirmed fraud entities!")
                    elif suspicious_nodes > 0:
                        st.warning(f"⚠️ **MEDIUM RISK**: This claim is connected to {suspicious_nodes} suspicious entities")
                    else:
                        st.success("✅ **LOW RISK**: No fraud or suspicious entities detected in immediate network")
                    
                    # Display performance
                    display_performance_metrics(timer, "Claim Network Analysis")
                    
                    st.markdown("---")
                    
                    # Graph controls
                    col_graph_title, col_rerender = st.columns([5, 1])
                    with col_graph_title:
                        st.markdown("#### 🎨 Interactive Network Graph")
                        st.caption("⭐ Star = New Claim | 🔴 Red = Confirmed Fraud | 🟠 Orange = Suspicious")
                    with col_rerender:
                        if st.button("🔄 Re-render", key="new_claim_rerender"):
                            st.rerun()
                    
                    # Render graph
                    config = create_enhanced_graph_config()
                    agraph(nodes, edges, config)
                    
                else:
                    st.info("Claim created as isolated node. Add service providers to see network connections.")
            
            # Reset button
            if st.button("📝 Create Another Claim", type="primary"):
                st.session_state.claim_submitted = False
                st.session_state.new_claim_id = None
                st.rerun()
        
        elif preview_button and not st.session_state.claim_submitted:
            st.info("💡 Submit the claim first to see its network visualization, or select existing entities to preview their connections.")



# -----------------------------------------------------------------------------
# Page 4: Admin Panel (Unchanged - keeping existing functionality)
# -----------------------------------------------------------------------------
elif page == "Admin Panel":
    st.title("⚙️ Admin Panel")
    st.markdown("Database management and data generation controls")
    
    # Display persistent admin messages
    if st.session_state.admin_message:
        if st.session_state.admin_message_type == "success":
            st.success(st.session_state.admin_message)
        elif st.session_state.admin_message_type == "error":
            st.error(st.session_state.admin_message)
        elif st.session_state.admin_message_type == "warning":
            st.warning(st.session_state.admin_message)
        elif st.session_state.admin_message_type == "info":
            st.info(st.session_state.admin_message)
    
    # Display generation log if available
    if st.session_state.generation_log:
        with st.expander("📋 Last Generation Log", expanded=True):
            st.text(st.session_state.generation_log)
    
    # Show database stats with refresh button
    col_title, col_refresh = st.columns([4, 1])
    with col_title:
        st.markdown("### 📊 Database Statistics")
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_stats"):
            # Clear any previous messages when manually refreshing
            st.session_state.admin_message = None
            st.session_state.admin_message_type = None
            st.rerun()
    
    try:
        stats = get_database_stats(driver)
        
        if stats['node_stats']:
            stats_df = pd.DataFrame(stats['node_stats'])
            
            col1, col2 = st.columns(2)
            with col1:
                st.dataframe(stats_df, use_container_width=True)
            
            with col2:
                if stats['fraud_stats']:
                    st.metric("Total Claims", stats['fraud_stats']["total_claims"])
                    st.metric("Labeled Fraud Claims", stats['fraud_stats']["fraud_claims"])
                    st.metric("Legitimate Claims", stats['fraud_stats']["legitimate_claims"])
                
                st.metric("Flagged Suspicious Entities", stats['suspicious_count'])
                st.metric("Total Relationships", stats['relationship_count'])
        else:
            st.info("Database is empty. Generate data below to get started.")
    
    except Exception as e:
        st.error(f"Error fetching statistics: {str(e)}")
    
    st.markdown("---")
    
    # Data Generation
    st.markdown("### 🏭 Data Generation")
    st.warning("⚠️ This will **clear all existing data** and generate fresh synthetic data")
    
    with st.form("data_generation_form"):
        st.markdown("#### Generation Parameters")
        
        col1, col2 = st.columns(2)
        with col1:
            num_legitimate = st.number_input("Legitimate Claims", 50, 500, 150)
            num_medical_mill = st.number_input("Medical Mill Rings", 1, 10, 3)
            num_kickback = st.number_input("Kickback Rings", 1, 10, 3)
        
        with col2:
            num_staged = st.number_input("Staged Accident Rings", 1, 10, 2)
            num_phantom = st.number_input("Phantom Passenger Rings", 1, 10, 3)
            num_adjuster_collusion = st.number_input("Adjuster Collusion Rings", 1, 10, 2)
        
        st.markdown("#### Implicit Fraud Patterns (Unlabeled)")
        st.info("""
        **Tiered patterns** align with detection thresholds for meaningful parameter exploration:
        - **Tier 1 (Borderline)**: At/below default thresholds — only detected with lowered settings
        - **Tier 2 (Moderate)**: Above thresholds — detected at default settings
        - **Tier 3 (Obvious)**: High values — clearly suspicious, always detected
        """)
        
        # Medical Mill tiers
        st.markdown("##### 🏥 Medical Mill")
        st.caption("Detection threshold: min_claims=5 | Tier 1: 3-4 claims, Tier 2: 5-7, Tier 3: 8-12")
        col_mm1, col_mm2, col_mm3 = st.columns(3)
        with col_mm1:
            impl_mm_t1 = st.number_input("Tier 1 (Borderline)", 0, 5, 2, key="impl_mm_t1")
        with col_mm2:
            impl_mm_t2 = st.number_input("Tier 2 (Moderate)", 0, 5, 2, key="impl_mm_t2")
        with col_mm3:
            impl_mm_t3 = st.number_input("Tier 3 (Obvious)", 0, 5, 1, key="impl_mm_t3")
        
        # Kickback tiers
        st.markdown("##### 🔧 Body Shop Kickback")
        st.caption("Detection threshold: min_shared=3 | Tier 1: 2 shared, Tier 2: 3-4, Tier 3: 5-8")
        col_kb1, col_kb2, col_kb3 = st.columns(3)
        with col_kb1:
            impl_kb_t1 = st.number_input("Tier 1 (Borderline)", 0, 5, 2, key="impl_kb_t1")
        with col_kb2:
            impl_kb_t2 = st.number_input("Tier 2 (Moderate)", 0, 5, 1, key="impl_kb_t2")
        with col_kb3:
            impl_kb_t3 = st.number_input("Tier 3 (Obvious)", 0, 5, 1, key="impl_kb_t3")
        
        # Staged Accident tiers
        st.markdown("##### 🚗 Staged Accident")
        st.caption("Detection threshold: min_staged=2 | Tier 1: 2 shared, Tier 2: 3-4, Tier 3: 5-6")
        col_sa1, col_sa2, col_sa3 = st.columns(3)
        with col_sa1:
            impl_sa_t1 = st.number_input("Tier 1 (Borderline)", 0, 5, 2, key="impl_sa_t1")
        with col_sa2:
            impl_sa_t2 = st.number_input("Tier 2 (Moderate)", 0, 5, 1, key="impl_sa_t2")
        with col_sa3:
            impl_sa_t3 = st.number_input("Tier 3 (Obvious)", 0, 5, 1, key="impl_sa_t3")
        
        # Phantom Passenger tiers
        st.markdown("##### 👻 Phantom Passenger")
        st.caption("Detection threshold: min_connections=3 | Tier 1: 2 connections, Tier 2: 3-4, Tier 3: 5-7")
        col_pp1, col_pp2, col_pp3 = st.columns(3)
        with col_pp1:
            impl_pp_t1 = st.number_input("Tier 1 (Borderline)", 0, 5, 2, key="impl_pp_t1")
        with col_pp2:
            impl_pp_t2 = st.number_input("Tier 2 (Moderate)", 0, 5, 1, key="impl_pp_t2")
        with col_pp3:
            impl_pp_t3 = st.number_input("Tier 3 (Obvious)", 0, 5, 1, key="impl_pp_t3")
        
        # Adjuster Collusion tiers
        st.markdown("##### 👔 Adjuster-Provider Collusion")
        st.caption("Detection threshold: min_adjuster=4 | Tier 1: 3 shared, Tier 2: 4-5, Tier 3: 6-8")
        col_ac1, col_ac2, col_ac3 = st.columns(3)
        with col_ac1:
            impl_ac_t1 = st.number_input("Tier 1 (Borderline)", 0, 5, 2, key="impl_ac_t1")
        with col_ac2:
            impl_ac_t2 = st.number_input("Tier 2 (Moderate)", 0, 5, 1, key="impl_ac_t2")
        with col_ac3:
            impl_ac_t3 = st.number_input("Tier 3 (Obvious)", 0, 5, 1, key="impl_ac_t3")

        # Near-miss legitimate patterns
        st.markdown("#### Near-Miss Legitimate Patterns")
        st.info("**False positive testing**: Legitimate patterns that look suspicious but aren't fraud")
        
        col_nm1, col_nm2, col_nm3 = st.columns(3)
        with col_nm1:
            nm_providers = st.number_input("High-Volume Providers", 0, 5, 3, key="nm_providers",
                                           help="Busy ERs/clinics with 4-5 claims (near threshold)")
        with col_nm2:
            nm_referrals = st.number_input("Repeat Referrals", 0, 5, 2, key="nm_referrals",
                                           help="Legitimate attorney-bodyshop pairs with 2 shared claims")
        with col_nm3:
            nm_witnesses = st.number_input("Repeat Witnesses", 0, 5, 3, key="nm_witnesses",
                                           help="Family/coworkers appearing in 2 claims together")
        
        generate_button = st.form_submit_button("🚀 Generate Data", type="primary")
    
    if generate_button:
        with st.spinner("Generating synthetic data... This may take a few minutes."):
            # Capture print output
            old_stdout = sys.stdout
            sys.stdout = buffer = io.StringIO()
            
            try:
                generator = FraudDataGenerator()
                
                # Clear database
                generator.clear_database()
                
                # Create indexes
                generator.create_indexes()
                
                # CRITICAL: Create shared entity pools FIRST
                generator.create_adjuster_pool(num_adjusters=20)
                generator.create_service_provider_pools()

                # Generate legitimate claims
                generator.create_legitimate_claims(num_claims=num_legitimate)
                
                # Generate explicit fraud patterns
                generator.create_medical_mill(num_rings=num_medical_mill)
                generator.create_bodyshop_kickback(num_rings=num_kickback)
                generator.create_staged_accident(num_rings=num_staged)
                generator.create_phantom_passenger(num_rings=num_phantom)
                generator.create_adjuster_collusion(num_rings=num_adjuster_collusion)
                
                # Generate tiered implicit fraud patterns
                tier_config = {
                    'medical_mill': {'tier1': impl_mm_t1, 'tier2': impl_mm_t2, 'tier3': impl_mm_t3},
                    'kickback': {'tier1': impl_kb_t1, 'tier2': impl_kb_t2, 'tier3': impl_kb_t3},
                    'staged': {'tier1': impl_sa_t1, 'tier2': impl_sa_t2, 'tier3': impl_sa_t3},
                    'phantom': {'tier1': impl_pp_t1, 'tier2': impl_pp_t2, 'tier3': impl_pp_t3},
                    'adjuster_collusion': {'tier1': impl_ac_t1, 'tier2': impl_ac_t2, 'tier3': impl_ac_t3}
                }
                generator.create_tiered_implicit_fraud_patterns(tier_config)
                
                # Generate near-miss legitimate patterns
                near_miss_config = {
                    'high_volume_providers': nm_providers,
                    'repeat_referrals': nm_referrals,
                    'repeat_witnesses': nm_witnesses
                }
                generator.create_near_miss_legitimate_patterns(near_miss_config)
                
                generator.close()
                
                # Get output
                output = buffer.getvalue()
                sys.stdout = old_stdout
                
                # Store message and log in session state
                st.session_state.admin_message = "✅ Data generation completed successfully!"
                st.session_state.admin_message_type = "success"
                st.session_state.generation_log = output
                
                # Refresh to show updated stats
                st.rerun()
            
            except Exception as e:
                sys.stdout = old_stdout
                st.session_state.admin_message = f"❌ Error during data generation: {str(e)}"
                st.session_state.admin_message_type = "error"
                st.session_state.generation_log = None
                st.rerun()
    
    st.markdown("---")
    
    # Database Management
    st.markdown("### 🗑️ Database Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Clear All Data")
        confirm_delete = st.checkbox("⚠️ I confirm I want to delete ALL data", key="confirm_delete")
        
        if st.button("🧹 Clear All Data", type="secondary", disabled=not confirm_delete):
            try:
                with driver.session() as session:
                    # Delete all nodes and relationships
                    session.run("MATCH (n) DETACH DELETE n")
                    
                    # Verify deletion
                    verify = session.run("MATCH (n) RETURN count(n) as remaining").single()
                    
                    if verify['remaining'] == 0:
                        st.session_state.admin_message = f"✅ Successfully deleted all data from database! Database is now empty."
                        st.session_state.admin_message_type = "success"
                        st.session_state.generation_log = None
                    else:
                        st.session_state.admin_message = f"⚠️ Deletion incomplete. {verify['remaining']} nodes remaining."
                        st.session_state.admin_message_type = "warning"
                        
                # Refresh to show updated stats and message
                st.rerun()
                        
            except Exception as e:
                st.session_state.admin_message = f"❌ Error clearing database: {str(e)}"
                st.session_state.admin_message_type = "error"
                st.rerun()
    
    with col2:
        st.markdown("#### Clear Detection Flags")
        if st.button("🔄 Clear Detection Flags", type="secondary"):
            try:
                with driver.session() as session:
                    # Clear suspicious flags
                    result1 = session.run("""
                        MATCH (n) WHERE n.suspicious = true
                        REMOVE n.suspicious, n.suspicion_type, n.suspicion_score
                        RETURN count(n) as count
                    """)
                    flagged_count = result1.single()["count"]
                    
                    # Clear degree centrality
                    result2 = session.run("""
                        MATCH (n) WHERE n.degree_centrality IS NOT NULL
                        REMOVE n.degree_centrality
                        RETURN count(n) as count
                    """)
                    centrality_count = result2.single()["count"]
                    
                    # Remove suspicious relationships
                    result3 = session.run("""
                        MATCH ()-[r:SUSPICIOUS_RELATIONSHIP]->()
                        DELETE r
                        RETURN count(r) as count
                    """)
                    rel_count = result3.single()["count"]
                
                st.session_state.admin_message = (
                    f"✅ Reset complete!\n"
                    f"• Cleared flags from {flagged_count} entities\n"
                    f"• Removed centrality from {centrality_count} nodes\n"
                    f"• Deleted {rel_count} suspicious relationships"
                )
                st.session_state.admin_message_type = "success"
                st.session_state.generation_log = None
                
                st.rerun()
            except Exception as e:
                st.session_state.admin_message = f"❌ Error clearing flags: {str(e)}"
                st.session_state.admin_message_type = "error"
                st.rerun()
    
    # Add a button to clear messages
    if st.session_state.admin_message:
        st.markdown("---")
        if st.button("🗑️ Clear Messages", key="clear_messages"):
            st.session_state.admin_message = None
            st.session_state.admin_message_type = None
            st.session_state.generation_log = None
            st.rerun()


# -----------------------------------------------------------------------------
# ENHANCED Sidebar legend with gradient colors
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Legend")

# Entity type colors (matching visualization)
st.sidebar.markdown("#### Entity Types")
st.sidebar.markdown("**Core Entity:**")
st.sidebar.markdown("⚫ **Claim** - Dark slate")

st.sidebar.markdown("**People (Involved Parties):**")
st.sidebar.markdown("🔵 **Claimant** - Bright blue")
st.sidebar.markdown("🔵 **Witness** - Light blue")

st.sidebar.markdown("**Company Personnel:**")
st.sidebar.markdown("🟢 **Adjuster** - Emerald green")

st.sidebar.markdown("**Service Providers:**")
st.sidebar.markdown("🟣 **Medical Provider** - Purple")
st.sidebar.markdown("🟠 **Attorney** - Dark orange")
st.sidebar.markdown("🟡 **Body Shop** - Golden yellow")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Risk Indicators")
st.sidebar.markdown("🔴 **Confirmed Fraud** - Bright red")
st.sidebar.markdown("   - Labeled fraud (ground truth)")
st.sidebar.markdown("   - Size: Large (35)")
st.sidebar.markdown("")
st.sidebar.markdown("🟠 **Suspicious** - Orange spectrum")
st.sidebar.markdown("   - Algorithm-detected patterns")
st.sidebar.markdown("   - Requires investigation")
st.sidebar.markdown("   - Yellow (20-40) → Amber (40-60)")
st.sidebar.markdown("   - Orange (60-80) → Dark Orange (80+)")
st.sidebar.markdown("   - Size: Medium (18-35)")
st.sidebar.markdown("")
st.sidebar.markdown("⚪ **Normal** - Base entity colors")
st.sidebar.markdown("   - No flags detected")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Node Features")
st.sidebar.markdown("**Size:**")
st.sidebar.markdown("● Large - High suspicion/fraud")
st.sidebar.markdown("● Medium - Moderate suspicion")
st.sidebar.markdown("● Small - Normal entity")
st.sidebar.markdown("")
st.sidebar.markdown("**Shape:**")
st.sidebar.markdown("⭐ Star - Root/Selected node")
st.sidebar.markdown("⚫ Dot - All other nodes")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎮 Controls")
st.sidebar.markdown("**Mouse:**")
st.sidebar.markdown("• 🖱️ Scroll - Zoom in/out")
st.sidebar.markdown("• 🖱️ Drag background - Pan view")
st.sidebar.markdown("• 🖱️ Drag nodes - Reposition")
st.sidebar.markdown("• 🖱️ Hover - Show details")
st.sidebar.markdown("")
st.sidebar.markdown("**Navigation:**")
st.sidebar.markdown("• Use navigation buttons")
st.sidebar.markdown("• Keyboard arrows to pan")

st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ About")
st.sidebar.info("Insurance Fraud Detection System using Neo4j graph analysis and pattern recognition algorithms.")