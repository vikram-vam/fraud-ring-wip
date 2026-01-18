"""
Main app code for stramlit UI
"""
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config
from neo4j import GraphDatabase
import pandas as pd
from datetime import datetime
import sys
import io

# Import custom modules
from fraud_detection import FraudDetector
from data_generator import FraudDataGenerator

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


# -----------------------------------------------------------------------------
# Graph visualization
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
    Create graph visualization from Neo4j records.
    
    Args:
        records: Neo4j query results
        entity_filters: List of entity types to include
        root_entity_id: ID of the root node (will be highlighted)
    """
    nodes = {}
    edges = []

    # Hierarchical color scheme - RED RESERVED FOR FRAUD ONLY
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
            color = color_map.get(label, color_map["Unknown"])
            size = 15
            title = f"{label}: {name}"
            
            # Check if this is the root node
            is_root = (root_entity_id and props.get("id") == root_entity_id)

            # FRAUD STATUS OVERRIDES EVERYTHING - RED ONLY FOR FRAUD
            # Priority: Confirmed Fraud > Suspicious > Normal Role Color
            if props.get("is_fraud"):
                # RED RESERVED FOR CONFIRMED FRAUD ONLY
                color = "#E74C3C"  # Bright red
                size = 28
                title += f"\n🚨 [FRAUD: {props.get('fraud_type', 'Unknown')}]"

            # Detected fraud (algorithm flagged) - Orange for suspicious
            elif props.get("suspicious"):
                color = "#E67E22"  # Dark orange (NOT red)
                size = 22
                title += (
                    f"\n⚠️ [SUSPICIOUS: {props.get('suspicion_type')}]"
                    f"\nScore: {props.get('suspicion_score')}"
                )
            
            # Highlight root node (but don't override fraud colors)
            if is_root:
                size = max(size, 30)  # Make root larger
                title = f"🎯 ROOT NODE\n{title}"

            nodes[node_id] = Node(
                id=str(node_id),
                label=name[:22],
                size=size,
                color=color,
                title=title,
                # Add special shape for root node
                shape="star" if is_root else "dot"
            )

        # Add edge
        if r["source_id"] in nodes and r["target_id"] in nodes:
            edges.append(
                Edge(
                    source=str(r["source_id"]),
                    target=str(r["target_id"]),
                    label=r["rel_type"],
                    type="CURVE_SMOOTH"
                )
            )

    return list(nodes.values()), edges


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.title("🔍 Fraud Detection System")
page = st.sidebar.radio(
    "Navigation",
    ["Network Discovery", "Fraud Ring Visualization", "New Claim", "Admin Panel"]
)

# -----------------------------------------------------------------------------
# Page 1: Network Discovery
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
    cols = st.columns(4)
    filters = {}
    for i, et in enumerate(entity_types):
        with cols[i % 4]:
            filters[et] = st.checkbox(et, True, key=f"filter_nd_{et}")

    active_filters = [k for k, v in filters.items() if v]

    if st.button("🔍 Explore Network", type="primary"):
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
                    root_entity_id=selected_entity[0]  # Pass root entity ID
                )
                
                st.markdown(f"### Network for **{selected_entity[1]}** (⭐ Root Node)")
                st.info(f"📊 Found {len(nodes)} nodes and {len(edges)} relationships within {hops} hop(s)")
                
                # Additional statistics
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    fraud_nodes = sum(1 for n in nodes if 'FRAUD' in n.title)
                    st.metric("Confirmed Fraud Nodes", fraud_nodes)
                with col_stat2:
                    suspicious_nodes = sum(1 for n in nodes if 'SUSPICIOUS' in n.title)
                    st.metric("Suspicious Nodes", suspicious_nodes)
                with col_stat3:
                    clean_nodes = len(nodes) - fraud_nodes - suspicious_nodes
                    st.metric("Clean Nodes", clean_nodes)
                
                config = Config(
                    width=1200, 
                    height=600, 
                    directed=False, 
                    physics=True,
                    hierarchical=False
                )
                agraph(nodes, edges, config)
                
                # Show network insights
                with st.expander("📊 Network Insights"):
                    st.markdown("#### Network Composition")
                    # Count nodes by type
                    node_types = {}
                    for node in nodes:
                        # Extract type from title
                        node_type = node.title.split(':')[0].replace('🎯 ROOT NODE\n', '').strip()
                        node_types[node_type] = node_types.get(node_type, 0) + 1
                    
                    df_composition = pd.DataFrame([
                        {"Entity Type": k, "Count": v} 
                        for k, v in sorted(node_types.items(), key=lambda x: x[1], reverse=True)
                    ])
                    st.dataframe(df_composition, use_container_width=True)
            else:
                st.warning("No relationships found for this entity with current filters.")
                st.info("💡 Try increasing the number of hops or enabling more entity type filters.")


# -----------------------------------------------------------------------------
# Page 2: Fraud Ring Visualization
# -----------------------------------------------------------------------------
elif page == "Fraud Ring Visualization":
    st.title("🚨 Fraud Ring Visualization")
    st.markdown("Analyze known fraud patterns and detect suspicious communities")

    tab1, tab2 = st.tabs(["Known Fraud Rings", "Fraud Detection"])

    with tab1:
        st.markdown("### Known Fraud Rings (Labeled Data)")
        st.info("These are explicitly labeled fraud patterns injected during data generation")

        fraud_types = ["All", "Medical Mill", "Body Shop Kickback", "Staged Accident", "Phantom Passenger"]
        selected_fraud = st.selectbox("Filter by Fraud Type", fraud_types)

        if st.button("🔍 Visualize Known Fraud Rings", type="primary"):
            with st.spinner("Loading fraud rings..."):
                records = get_fraud_rings(driver, selected_fraud)

                if records:
                    entity_types = get_entity_types(driver)
                    nodes, edges = create_graph_visualization(records, entity_types)

                    st.markdown(f"### Fraud Network: **{selected_fraud}**")
                    st.info(f"📊 Found {len(nodes)} nodes and {len(edges)} relationships")

                    config = Config(
                        width=1200,
                        height=600,
                        directed=False,
                        physics=True,
                        hierarchical=False
                    )

                    agraph(nodes, edges, config)

                    st.markdown("### 🔴 Legend")
                    st.markdown("- **Red nodes**: Confirmed fraudulent entities")
                    st.markdown("- **Node size**: Indicates fraud involvement")
                else:
                    st.warning("No fraud rings found. Generate data first using Admin Panel.")

    with tab2:
        st.markdown("### Fraud Detection Algorithms")
        st.markdown("Run advanced algorithms to detect **unlabeled** suspicious patterns")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Detection Parameters")
            min_claims = st.number_input("Medical Mill - Min Claims", 3, 20, 5)
            min_shared = st.number_input("Kickback - Min Shared Claims", 2, 10, 3)
        
        with col2:
            st.markdown("#### ")
            min_staged = st.number_input("Staged Accident - Min Shared", 2, 10, 2)
            min_phantom = st.number_input("Phantom - Min Connections", 2, 10, 3)

        if st.button("🚨 Run All Fraud Detection Algorithms", type="primary"):
            with st.spinner("Running fraud detection algorithms..."):
                # Capture print output
                old_stdout = sys.stdout
                sys.stdout = buffer = io.StringIO()
                
                try:
                    detector = FraudDetector()
                    results = detector.run_all_detections()
                    detector.close()
                    
                    # Get output
                    output = buffer.getvalue()
                    sys.stdout = old_stdout
                    
                    st.success("✅ Fraud detection completed successfully!")

                    # Show summary
                    summary = {
                        "Medical Mills": len(results["medical_mills"]),
                        "Body Shop Kickbacks": len(results["kickbacks"]),
                        "Staged Accidents": len(results["staged_accidents"]),
                        "Phantom Passengers": len(results["phantom_passengers"]),
                    }

                    st.markdown("### 📊 Detection Summary")
                    summary_df = pd.DataFrame([
                        {"Fraud Type": k, "Detected Cases": v} 
                        for k, v in summary.items()
                    ])
                    st.dataframe(summary_df, use_container_width=True)

                    # Show flagged entities
                    with driver.session() as session:
                        flagged = session.run("""
                        MATCH (n)
                        WHERE n.suspicious = true
                        RETURN labels(n)[0] AS type,
                               n.name AS name,
                               n.suspicion_type AS fraud_type,
                               n.suspicion_score AS score
                        ORDER BY score DESC
                        LIMIT 20
                        """).data()

                    if flagged:
                        st.markdown("### 🚩 Top 20 Suspicious Entities")
                        flagged_df = pd.DataFrame(flagged)
                        st.dataframe(flagged_df, use_container_width=True)
                    
                    # Show console output
                    with st.expander("📋 Detection Log"):
                        st.text(output)
                    
                    # Visualize suspicious communities
                    st.markdown("### 🔍 Visualize Suspicious Communities")
                    if st.button("Show Suspicious Network"):
                        with st.spinner("Loading suspicious communities..."):
                            records = get_suspicious_communities(driver)
                            
                            if records:
                                entity_types = get_entity_types(driver)
                                nodes, edges = create_graph_visualization(records, entity_types)
                                
                                st.info(f"📊 Found {len(nodes)} suspicious nodes and {len(edges)} relationships")
                                
                                config = Config(
                                    width=1200,
                                    height=600,
                                    directed=False,
                                    physics=True,
                                    hierarchical=False
                                )
                                
                                agraph(nodes, edges, config)
                            else:
                                st.warning("No suspicious communities detected")
                
                except Exception as e:
                    sys.stdout = old_stdout
                    st.error(f"Error during fraud detection: {str(e)}")


# -----------------------------------------------------------------------------
# Page 3: New Claim
# -----------------------------------------------------------------------------
elif page == "New Claim":
    st.title("📝 New Claim Submission")
    st.markdown("Submit a new insurance claim and analyze its fraud propensity")

    with st.form("new_claim_form"):
        st.markdown("### Claim Details")
        col1, col2 = st.columns(2)

        with col1:
            claim_id = st.text_input(
                "Claim ID",
                value=f"CLM_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            claim_type = st.selectbox(
                "Claim Type",
                ["Auto", "Property", "Medical", "Liability"]
            )
            claim_amount = st.number_input("Claim Amount ($)", min_value=0.0, value=5000.0, step=100.0)

        with col2:
            claim_name = st.text_input("Description", "New Insurance Claim")
            claim_date = st.date_input("Claim Date", datetime.now())

        st.markdown("### Associated Entities")
        col3, col4 = st.columns(2)
        
        with col3:
            claimant_id = st.text_input("Claimant ID", f"P_{datetime.now().strftime('%H%M%S')}")
            claimant_name = st.text_input("Claimant Name", "")
        
        with col4:
            adjuster_id = st.text_input("Adjuster ID", "ADJ_001")
            adjuster_name = st.text_input("Adjuster Name", "John Adjuster")

        submitted = st.form_submit_button("✅ Submit Claim", type="primary")

    if submitted:
        if not claimant_name:
            st.error("⚠️ Claimant name is required")
        else:
            try:
                with driver.session() as session:
                    session.run(
                        """
                        CREATE (c:Claim {
                            id: $claim_id,
                            name: $claim_name,
                            claim_amount: $claim_amount,
                            claim_date: $claim_date,
                            claim_type: $claim_type,
                            is_fraud: false
                        })
                        MERGE (p:Person:Claimant {id: $claimant_id})
                        ON CREATE SET p.name = $claimant_name
                        ON MATCH SET p.name = $claimant_name
                        MERGE (a:Person:Adjuster {id: $adjuster_id})
                        ON CREATE SET a.name = $adjuster_name
                        ON MATCH SET a.name = $adjuster_name
                        CREATE (c)-[:FILED_BY]->(p)
                        CREATE (c)-[:HANDLED_BY]->(a)
                        """,
                        claim_id=claim_id,
                        claim_name=claim_name,
                        claim_amount=claim_amount,
                        claim_date=claim_date.isoformat(),
                        claim_type=claim_type,
                        claimant_id=claimant_id,
                        claimant_name=claimant_name,
                        adjuster_id=adjuster_id,
                        adjuster_name=adjuster_name,
                    )

                st.success(f"✅ Claim **{claim_id}** created successfully!")
                
                # Auto-visualize the claim
                st.markdown("### Claim Network Analysis")
                st.info("Analyzing the claim's network to assess fraud propensity...")
                
                hops = st.slider("Neighborhood Hops", 1, 5, 2, key="new_claim_hops")
                
                if st.button("🔍 Visualize Claim Network"):
                    with st.spinner("Loading claim neighborhood..."):
                        entity_types = get_entity_types(driver)
                        records = get_neighborhood(driver, "Claim", claim_id, hops, entity_types)
                        
                        if records:
                            nodes, edges = create_graph_visualization(
                                records, 
                                entity_types,
                                root_entity_id=claim_id
                            )
                            
                            st.info(f"📊 Found {len(nodes)} nodes and {len(edges)} relationships within {hops} hops")
                            
                            # Check for suspicious connections
                            suspicious_count = sum(1 for n in nodes if 'SUSPICIOUS' in n.title or 'FRAUD' in n.title)
                            if suspicious_count > 0:
                                st.warning(f"⚠️ WARNING: Found {suspicious_count} suspicious/fraudulent entities in network!")
                            else:
                                st.success("✅ No suspicious entities detected in immediate network")
                            
                            config = Config(
                                width=1200,
                                height=600,
                                directed=False,
                                physics=True,
                                hierarchical=False
                            )
                            
                            agraph(nodes, edges, config)
                        else:
                            st.info("Claim created as isolated node. No existing relationships found.")
                
            except Exception as e:
                st.error(f"Error creating claim: {str(e)}")


# -----------------------------------------------------------------------------
# Page 4: Admin Panel
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
        
        st.markdown("#### Implicit Fraud Patterns (Unlabeled)")
        st.info("Configure how many unlabeled fraud patterns to generate for each type")
        
        col3, col4 = st.columns(2)
        with col3:
            implicit_medical_mill = st.number_input("Implicit Medical Mill", 0, 10, 2, key="impl_mm")
            implicit_kickback = st.number_input("Implicit Kickback", 0, 10, 1, key="impl_kb")
        with col4:
            implicit_staged = st.number_input("Implicit Staged Accident", 0, 10, 1, key="impl_sa")
            implicit_phantom = st.number_input("Implicit Phantom Passenger", 0, 10, 1, key="impl_pp")
        
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
                
                # Generate legitimate claims
                generator.create_legitimate_claims(num_claims=num_legitimate)
                
                # Generate explicit fraud patterns
                generator.create_medical_mill(num_rings=num_medical_mill)
                generator.create_bodyshop_kickback(num_rings=num_kickback)
                generator.create_staged_accident(num_rings=num_staged)
                generator.create_phantom_passenger(num_rings=num_phantom)
                
                # Generate implicit patterns with granular control
                implicit_config = {
                    'medical_mill': implicit_medical_mill,
                    'kickback': implicit_kickback,
                    'staged': implicit_staged,
                    'phantom': implicit_phantom
                }
                generator.create_implicit_fraud_patterns(pattern_config=implicit_config)
                
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
                    result = session.run("""
                    MATCH (n) WHERE n.suspicious = true
                    REMOVE n.suspicious, n.suspicion_type, n.suspicion_score
                    RETURN count(n) as count
                    """)
                    count = result.single()["count"]
                
                st.session_state.admin_message = f"✅ Cleared suspicious flags from {count} entities!"
                st.session_state.admin_message_type = "success"
                st.session_state.generation_log = None
                
                # Refresh stats
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
# Sidebar legend with correct colors
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Legend")

# Entity type colors (matching visualization)
st.sidebar.markdown("#### Entity Types")
st.sidebar.markdown("**Core Entity:**")
st.sidebar.markdown("⬛ **Claim** (#2C3E50) - Dark slate")

st.sidebar.markdown("**People (Involved Parties):**")
st.sidebar.markdown("🔵 **Claimant** (#3498DB) - Bright blue")
st.sidebar.markdown("🔷 **Witness** (#5DADE2) - Light blue")

st.sidebar.markdown("**Company Personnel:**")
st.sidebar.markdown("🟢 **Adjuster** (#27AE60) - Emerald green")

st.sidebar.markdown("**Service Providers:**")
st.sidebar.markdown("🟣 **Medical Provider** (#9B59B6) - Purple")
st.sidebar.markdown("🟠 **Attorney** (#E67E22) - Dark orange")
st.sidebar.markdown("🟡 **Body Shop** (#F39C12) - Golden yellow")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Risk Indicators")
st.sidebar.markdown("🔴 **RED** - Confirmed Fraud (ONLY)")
st.sidebar.markdown("   - Color: #E74C3C")
st.sidebar.markdown("   - Overrides all base colors")
st.sidebar.markdown("🟠 **Dark Orange** - Suspicious (detected)")
st.sidebar.markdown("   - Color: #E67E22")
st.sidebar.markdown("   - Algorithm-flagged entities")
st.sidebar.markdown("⚪ **Base Colors** - Normal entities")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Node Size & Shape")
st.sidebar.markdown("**Size:**")
st.sidebar.markdown("● **Large (28px)** - Confirmed fraud")
st.sidebar.markdown("● **Medium (22px)** - Suspicious")
st.sidebar.markdown("● **Small (15px)** - Normal")
st.sidebar.markdown("")
st.sidebar.markdown("**Shape:**")
st.sidebar.markdown("⭐ **Star** - Root/Selected entity")
st.sidebar.markdown("⚫ **Dot** - All other entities")

st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ About")
st.sidebar.info("Insurance Fraud Detection System using Neo4j graph analysis and pattern recognition algorithms.")