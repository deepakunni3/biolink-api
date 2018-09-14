from neo4j.v1 import GraphDatabase, basic_auth
from cachier import cachier
import datetime

from biolink.settings import get_biolink_config

url = get_biolink_config()['alliance_neo4j']['url']
username = get_biolink_config()['alliance_neo4j']['username']
password = get_biolink_config()['alliance_neo4j']['password']

taxon_map = {}

type_map = {
    'gene': 'Gene',
    'goterm': 'GOTerm'
}

def get_taxon_map():
    """
    Get all Species nodes from Neo4j and generate a taxonId to name map
    """
    driver = GraphDatabase.driver(url, auth=(username, password))
    session = driver.session()

    global taxon_map
    if not taxon_map:
        results = session.run("MATCH (n:Species) RETURN n")
        for r in results:
            node = r.get('n')
            taxon_map[node.get('primaryKey')] = node.get('name')
    return taxon_map

def get_entity(primaryKey, type=None):
    """
    Given a primaryKey and type, get a matching node from Neo4j
    """
    driver = GraphDatabase.driver(url, auth=(username, password))
    session = driver.session()

    json_obj = {}
    if type is None:
        query = "MATCH (g {{ primaryKey:'{}' }}) return g".format(primaryKey)
    else:
        query = "MATCH (g:{} {{ primaryKey:'{}' }}) return g".format(type_map[type], primaryKey)
    results = session.run(query)

    for r in results:
        node = r.get('g')
        json_obj['id'] = node.get('primaryKey')
        json_obj['label'] = node.get('name')
        json_obj['categories'] = [node.get('type')]
        if node.get('taxonId'):
            json_obj['taxon'] = {
                'id': node.get('taxonId'),
                'label': get_taxon_map()[node.get('taxonId')]
            }
        if node.get('definition'):
            json_obj['description'] = node.get('definition')

    return json_obj

def get_gene_to_expression(primaryKey):
    """
    Given a Gene primaryKey, get all gene to expression associations from Neo4j
    """
    driver = GraphDatabase.driver(url, auth=(username, password))
    session = driver.session()

    query = """
    MATCH p1=(g:Gene)-->(s:BioEntityGeneExpressionJoin)--(t) WHERE g.primaryKey = '{}'
    MATCH p2=(t:ExpressionBioEntity)--(o:EMAPATerm)
    RETURN p1,p2
    """.format(primaryKey)

    results = session.run(query)
    # TODO

def get_gene_to_phenotype(primaryKey):
    """
    Given a Gene primaryKey, get all gene to phenotype associations from Neo4j
    """
    driver = GraphDatabase.driver(url, auth=(username, password))
    session = driver.session()

    query = "MATCH p=(g:Gene)-->(t:Phenotype) WHERE g.primaryKey = '{}' RETURN p1".format(primaryKey)
    results = session.run(query)

    json_obj = {'associations': []}
    for r in results:
        for rel in r.get("p").relationships:
            start_node = rel.start_node
            end_node = rel.end_node
            association = {}
            association['id'] = rel.id
            association['subject'] = {
                'id': start_node.get('primaryKey'),
                'label': start_node.get('symbol'),
                'taxon': {
                    'id': start_node.get('taxonId'),
                    'label': get_taxon_map()[start_node.get('taxonId')]
                }
            }
            association['object'] = {
                'id': end_node.id,
                'label': end_node.get('primaryKey')
            }
            association['relation'] = {
                'id': rel.get('uuid'),
                'label': rel.type
            }
            json_obj['associations'].append(association)

    return json_obj

@cachier(stale_after=datetime.timedelta(days=2))
def get_node_graph(primaryKey, limit=None):
    """
    Given a primaryKey, get all linked nodes and return as a graph
    """
    driver = GraphDatabase.driver(url, auth=(username, password))
    session = driver.session()

    query = "MATCH p=(s {{ primaryKey: '{}' }})-[r]-(o) RETURN p".format(primaryKey)
    if limit:
        query += " LIMIT {}".format(limit)
    results = session.run(query)

    nodes = []
    edges = []
    seen = []
    for r in results:
        for rel in r.get("p").relationships:
            start_node = rel.start_node
            end_node = rel.end_node

            if start_node.id not in seen:
                seen.append(start_node.get('id'))
                node_obj = {
                    'id': start_node.get('primaryKey'),
                    'lbl': start_node.get('name')
                }
                nodes.append(node_obj)

            if end_node.id not in seen:
                seen.append(end_node.get('id'))
                node_obj = {
                    'id': end_node.get('primaryKey'),
                    'lbl': end_node.get('name')
                }
                nodes.append(node_obj)

            edge_obj = {
                'sub': start_node.get('primaryKey'),
                'pred': rel.type,
                'obj': end_node.get('primaryKey')
            }

            edges.append(edge_obj)

    obj = {
        'nodes': nodes,
        'edges': edges
    }

    return obj



