import logging

from flask import request
from flask_restplus import Resource
from biolink.datamodel.serializers import association, bbop_graph
from scigraph.scigraph_util import SciGraph
from biolink.api.restplus import api
from alliance.alliance_neo4j import get_node_graph

from biolink.settings import get_current_instance, get_biolink_config

log = logging.getLogger(__name__)

ns = api.namespace('graph', description='Operations over data graphs')

parser = api.parser()
sg = SciGraph()

@ns.route('/node/<id>')
@api.doc(params={'id': 'CURIE e.g. MGI:97364'})
class NodeResource(Resource):

    @api.expect(parser)
    @api.marshal_list_with(bbop_graph)
    def get(self, id):
        """
        Returns a graph node.

        A node is an abstract representation of some kind of entity. The entity may be a physical thing such as a patient,
        a molecular entity such as a gene or protein, or a conceptual entity such as a class from an ontology.
        """
        args = parser.parse_args()

        if get_current_instance(get_biolink_config())['id'] == 'Alliance':
            obj = get_node_graph(id)
        else:
            obj = sg.graph(id)
        return obj

@ns.route('/edges/from/<id>', doc=False)
@api.doc(params={'id': 'CURIE e.g. HP:0000465'})
class EdgeResource(Resource):

    @api.expect(parser)
    @api.marshal_list_with(bbop_graph)
    def get(self, id):
        """
        Returns edges emanating from a node. 

        """
        args = parser.parse_args()
        
        return sg.graph(id)
    
