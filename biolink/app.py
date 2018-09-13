import logging.config
import os

import flask as f
from flask import Flask, Blueprint, request
from flask import render_template
from flask_cors import CORS, cross_origin
from biolink import settings

biolink_config = settings.get_config()
current_instance = None
for instance in biolink_config['instances']:
    if instance['current']:
        current_instance = instance

# /bioentity
if 'biolink.api.bio.endpoints.bioentity' in current_instance['enabled_namespace']:
    from biolink.api.bio.endpoints.bioentity import ns as bio_objects_namespace
# /associations/from
if 'biolink.api.link.endpoints.associations_from' in current_instance['enabled_namespace']:
    from biolink.api.link.endpoints.associations_from import ns as associations_from_namespace
# /associations/find_associations
if 'biolink.api.link.endpoints.find_associations' in current_instance['enabled_namespace']:
    from biolink.api.link.endpoints.find_associations import ns as find_associations_namespace
# /entitysearch
if 'biolink.api.search.endpoints.entitysearch' in current_instance['enabled_namespace']:
    from biolink.api.search.endpoints.entitysearch import ns as entity_search_namespace
# /ontol/subgraph
if 'biolink.api.ontol.endpoints.subgraph' in current_instance['enabled_namespace']:
    from biolink.api.ontol.endpoints.subgraph import ns as ontol_subgraph_namespace
# /ontol/information_content
if 'biolink.api.ontol.endpoints.termstats' in current_instance['enabled_namespace']:
    from biolink.api.ontol.endpoints.termstats import ns as ontol_termstats_namespace
# /ontol/labeler
if 'biolink.api.ontol.endpoints.labeler' in current_instance['enabled_namespace']:
    from biolink.api.ontol.endpoints.labeler import ns as ontol_labeler
# /ontol/enrichment
if 'biolink.api.ontol.endpoints.enrichment' in current_instance['enabled_namespace']:
    from biolink.api.ontol.endpoints.enrichment import ns as ontol_enrichment_namespace
# /bioentityset
if 'biolink.api.entityset.endpoints.summary' in current_instance['enabled_namespace']:
    from biolink.api.entityset.endpoints.summary import ns as entityset_summary_namespace
# /bioentityset/slimmer
if 'biolink.api.entityset.endpoints.slimmer' in current_instance['enabled_namespace']:
    from biolink.api.entityset.endpoints.slimmer import ns as entityset_slimmer_namespace
# /bioentityset/homologs
if 'biolink.api.entityset.endpoints.geneset_homologs' in current_instance['enabled_namespace']:
    from biolink.api.entityset.endpoints.geneset_homologs import ns as geneset_homologs_namespace
# /bioentityset/overrepresentation
if 'biolink.api.entityset.endpoints.overrepresentation' in current_instance['enabled_namespace']:
    from biolink.api.entityset.endpoints.overrepresentation import ns as overrepresentation
# /nlp/annotate
if 'biolink.api.nlp.endpoints.annotate' in current_instance['enabled_namespace']:
    from biolink.api.nlp.endpoints.annotate import ns as nlp_annotate_namespace
# /graph/node
if 'biolink.api.graph.endpoints.node' in current_instance['enabled_namespace']:
    from biolink.api.graph.endpoints.node import ns as graph_node_namespace
# /ontol/subgraph/
if 'biolink.api.ontol.endpoints.subgraph' in current_instance['enabled_namespace']:
    from biolink.api.ontol.endpoints.subgraph import ns as subgraph_namespace
# /mart
if 'biolink.api.mart.endpoints.mart' in current_instance['enabled_namespace']:
    from biolink.api.mart.endpoints.mart import ns as mart_namespace
# /cam
if 'biolink.api.cam.endpoints.cam_endpoint' in current_instance['enabled_namespace']:
    from biolink.api.cam.endpoints.cam_endpoint import ns as cam_namespace
# /owl/ontology
if 'biolink.api.owl.endpoints.ontology' in current_instance['enabled_namespace']:
    from biolink.api.owl.endpoints.ontology import ns as owl_ontology_namespace
# /individual
if 'biolink.api.patient.endpoints.individual' in current_instance['enabled_namespace']:
    from biolink.api.patient.endpoints.individual import ns as patient_individual_namespace
# /identifier/prefixes
if 'biolink.api.identifier.endpoints.prefixes' in current_instance['enabled_namespace']:
    from biolink.api.identifier.endpoints.prefixes import ns as identifier_prefixes_namespace
# /identifier/mapper
if 'biolink.api.identifier.endpoints.mapper' in current_instance['enabled_namespace']:
    from biolink.api.identifier.endpoints.mapper import ns as identifier_prefixes_mapper
# /genome/features
if 'biolink.api.genome.endpoints.region' in current_instance['enabled_namespace']:
    from biolink.api.genome.endpoints.region import ns as genome_region_namespace
# /pair/sim
if 'biolink.api.pair.endpoints.pairsim' in current_instance['enabled_namespace']:
    from biolink.api.pair.endpoints.pairsim import ns as pair_pairsim_namespace
# /evidence/graph
if 'biolink.api.evidence.endpoints.graph' in current_instance['enabled_namespace']:
    from biolink.api.evidence.endpoints.graph import ns as evidence_graph_namespace
# /relation/usage
if 'biolink.api.relations.endpoints.relation_usage' in current_instance['enabled_namespace']:
    from biolink.api.relations.endpoints.relation_usage import ns as relation_usage_namespace
# /variation/set
if 'biolink.api.variation.endpoints.variantset' in current_instance['enabled_namespace']:
    from biolink.api.variation.endpoints.variantset import ns as variation_variantset_namespace
# /pub/pubs
if 'biolink.api.pub.endpoints.pubs' in current_instance['enabled_namespace']:
    from biolink.api.pub.endpoints.pubs import ns as pubs_namespace


from biolink.api.restplus import api

from biolink.database import db

app = Flask(__name__)
CORS(app)
logging.config.fileConfig('logging.conf')
log = logging.getLogger(__name__)


#def configure_app(flask_app):
#app.config['SERVER_NAME'] = settings.FLASK_SERVER_NAME
app.config['SQLALCHEMY_DATABASE_URI'] = settings.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = settings.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['SWAGGER_UI_DOC_EXPANSION'] = settings.RESTPLUS_SWAGGER_UI_DOC_EXPANSION
app.config['RESTPLUS_VALIDATE'] = settings.RESTPLUS_VALIDATE
app.config['RESTPLUS_MASK_SWAGGER'] = settings.RESTPLUS_MASK_SWAGGER
app.config['ERROR_404_HELP'] = settings.RESTPLUS_ERROR_404_HELP


#def initialize_app(flask_app):
#    configure_app(flask_app)

blueprint = Blueprint('api', __name__, url_prefix='/api')
api.init_app(blueprint)
# remove 'default' namespace
api.namespaces.pop(0)
app.register_blueprint(blueprint)
db.init_app(app)

# initial setup
#from ontobio.ontol_factory import OntologyFactory
#factory = OntologyFactory()
#ont = factory.create()


@app.route("/")
def hello():
    return render_template('index.html', base_url=request.base_url)

def main():
    #initialize_app(app)
    log.info('>>>>> Starting development server at http://{}/api/ <<<<<'.format(app.config['SERVER_NAME']))
    app.run(debug=settings.FLASK_DEBUG)

if __name__ == "__main__":
    main()
