import logging

from flask import request
from flask_restplus import Resource, inputs
from biolink.datamodel.serializers import node, named_object, bio_object, association_results, association, publication, gene, substance, genotype, allele, search_result
#import biolink.datamodel.serializers
from biolink.api.restplus import api
from ontobio.golr.golr_associations import search_associations, search_associations_go, select_distinct_subjects, get_homologs
from scigraph.scigraph_util import SciGraph
from biowikidata.wd_sparql import doid_to_wikidata, resolve_to_wikidata, condition_to_drug
from ontobio.vocabulary.relations import HomologyTypes
from ..closure_bins import create_closure_bin

from biolink.settings import get_current_instance, get_config
from alliance.alliance_neo4j import get_entity, get_gene_to_expression, get_gene_to_phenotype

from biolink import USER_AGENT

from ontobio.golr.golr_query import run_solr_text_on, ESOLR, ESOLRDoc, replace
from ontobio.config import get_config
import json


log = logging.getLogger(__name__)

ns = api.namespace('bioentity', description='Retrieval of domain entities plus associations')


basic_parser = api.parser()
basic_parser.add_argument('start', type=int, required=False, default=0, help='beginning row')
basic_parser.add_argument('rows', type=int, required=False, default=100, help='number of rows')
basic_parser.add_argument('evidence', action='append', help='Object id, e.g. ECO:0000501 (for IEA; Includes inferred by default) or a specific publication or other supporting object, e.g. ZFIN:ZDB-PUB-060503-2')


core_parser = api.parser()
core_parser.add_argument('rows', type=int, required=False, default=100, help='number of rows')
core_parser.add_argument('start', type=int, required=False, help='beginning row')
core_parser.add_argument('unselect_evidence', type=inputs.boolean, default=False, help='If true, excludes evidence objects in response')
core_parser.add_argument('exclude_automatic_assertions', type=inputs.boolean, default=False, help='If true, excludes associations that involve IEAs (ECO:0000501)')
core_parser.add_argument('fetch_objects', type=inputs.boolean, default=True, help='If true, returns a distinct set of association.objects (typically ontology terms). This appears at the top level of the results payload')
core_parser.add_argument('use_compact_associations', type=inputs.boolean, default=False, help='If true, returns results in compact associations format')
core_parser.add_argument('slim', action='append', help='Map objects up (slim) to a higher level category. Value can be ontology class ID or subset ID')
core_parser.add_argument('evidence', help='Object id, e.g. ECO:0000501 (for IEA; Includes inferred by default) or a specific publication or other supporting object, e.g. ZFIN:ZDB-PUB-060503-2')

INVOLVED_IN = 'involved_in'
INVOLVED_IN_REGULATION_OF = 'involved_in_regulation_of'
ACTS_UPSTREAM_OF_OR_WITHIN = 'acts_upstream_of_or_within'
TYPE_GENE = 'gene'
TYPE_VARIANT = 'variant'
TYPE_GENOTYPE = 'genotype'
TYPE_PHENOTYPE = 'phenotype'
TYPE_DISEASE = 'disease'
TYPE_GOTERM = 'goterm'
TYPE_PATHWAY = 'pathway'
TYPE_ANATOMY = 'anatomy'
TYPE_SUBSTANCE = 'substance'
TYPE_INDIVIDUAL = 'individual'

core_parser_with_rel = core_parser.copy()
core_parser_with_rel.add_argument('relationship_type', choices=[INVOLVED_IN, INVOLVED_IN_REGULATION_OF, ACTS_UPSTREAM_OF_OR_WITHIN], default=INVOLVED_IN, help="relationship type ('{}', '{}' or '{}')".format(INVOLVED_IN, INVOLVED_IN_REGULATION_OF, ACTS_UPSTREAM_OF_OR_WITHIN))

homolog_parser = core_parser.copy()
homolog_parser.add_argument('homolog_taxon', help='Taxon CURIE of homolog, e.g. NCBITaxon:9606 (Can be an ancestral node in the ontology; includes inferred associations, by default)')
homolog_parser.add_argument('homology_type', choices=['P', 'O', 'LDO'], help='P (paralog), O (Ortholog) or LDO (least-diverged ortholog)')

scigraph = SciGraph('https://scigraph-data.monarchinitiative.org/scigraph/')

homol_rel = HomologyTypes.Homolog.value

SHOW_ROUTE = None
if get_current_instance(get_config())['id'] == 'Alliance':
    SHOW_ROUTE = False

def get_object_gene(id, **args):
        obj = scigraph.bioobject(id, 'Gene')
        obj.phenotype_associations = search_associations(subject=id, object_category='phenotype', user_agent=USER_AGENT, **args)['associations']
        obj.homology_associations = search_associations(subject=id, rel=homol_rel, object_category='gene', user_agent=USER_AGENT, **args)['associations']
        obj.disease_associations = search_associations(subject=id, object_category='disease', user_agent=USER_AGENT, **args)['associations']
        obj.genotype_associations = search_associations(subject=id, invert_subject_object=True, object_category='genotype', user_agent=USER_AGENT, **args)['associations']

        return(obj)

def get_object_genotype(id, **args):
        obj = scigraph.bioobject(id, 'Genotype')
        obj.phenotype_associations = search_associations(subject=id, object_category='phenotype', user_agent=USER_AGENT, **args)['associations']
        obj.disease_associations = search_associations(subject=id, object_category='disease', user_agent=USER_AGENT, **args)['associations']
        obj.gene_associations = search_associations(subject=id, object_category='gene', user_agent=USER_AGENT, **args)['associations']

        return(obj)

@ns.route('/<id>')
@api.doc(params={'id': 'id, e.g. NCBIGene:84570'})
class GenericObject(Resource):

    @api.expect(core_parser)
    @api.marshal_with(bio_object)
    def get(self, id):
        """
        Returns basic info on object of any type
        """
        if get_current_instance(get_config())['id'] == 'Alliance':
            obj = get_entity(id)
        else:
            obj = scigraph.bioobject(id)
        return(obj)

@ns.route('/<type>/<id>')
@api.param('id', 'id, e.g. MGI:97364')
@api.param('type', 'bioentity type', enum=[TYPE_GENE, TYPE_VARIANT, TYPE_GENOTYPE, TYPE_PHENOTYPE,
                                           TYPE_DISEASE, TYPE_GOTERM, TYPE_PATHWAY, TYPE_ANATOMY,
                                           TYPE_SUBSTANCE, TYPE_INDIVIDUAL])
class GenericObjectByType(Resource):

    @api.expect(core_parser)
    @api.marshal_with(bio_object)
    def get(self, id, type):
        """
        Return basic info on an object for a given type
        """
        if get_current_instance(get_config())['id'] == 'Alliance':
            obj = get_entity(id, type)
        else:
            obj = scigraph.bioobject(id)
        return (obj)

@ns.route('/<id>/associations', doc=SHOW_ROUTE)
class GenericAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns associations for an entity regardless of the type
        """
        return search_associations(
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/interactions', doc=SHOW_ROUTE)
@api.doc(params={'id': 'id, e.g. NCBIGene:3630. Equivalent IDs can be used with same results'})
class GeneInteractions(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns interactions for a gene
        """
        return search_associations(
            subject_category='gene',
            object_category='gene',
            relation='RO:0002434',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/homologs', doc=SHOW_ROUTE)
@api.doc(params={'id': 'id, e.g. NCBIGene:3630. Equivalent IDs can be used with same results'})
class GeneHomologAssociations(Resource):

    @api.expect(homolog_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns homologs for a gene
        """
        """
        Horrible hacks
        """
        id = id.replace('WB:', 'WormBase:', 1)
        id = id.replace('WormBaseGene', 'WBGene', 1)

        logging.info("looking for homologs to {}".format(id))

        homolog_args = homolog_parser.parse_args()
        return search_associations(
            subject_category='gene',
            object_category='gene',
            relation=homol_rel,
            subject=id,
            object_taxon=homolog_args.homolog_taxon,
            user_agent=USER_AGENT,
            **homolog_args
        )

@ns.route('/gene/<id>/phenotypes')
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750. Equivalent IDs can be used with same results'})
class GenePhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns phenotypes associated with gene
        """
        results = None
        if get_current_instance(get_config())['id'] == 'Alliance':
            results = get_gene_to_phenotype(id)
        else:
            results = search_associations(
                subject_category='gene',
                object_category='phenotype',
                subject=id,
                user_agent=USER_AGENT,
                **core_parser.parse_args()
            )

        return results


@ns.route('/gene/<id>/diseases', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750. Equivalent IDs can be used with same results'})
class GeneDiseaseAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns diseases associated with gene
        """

        return search_associations(
            subject_category='gene',
            object_category='disease',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/pathways', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:50846. Equivalent IDs can be used with same results'})
class GenePathwayAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns pathways associated with gene
        """

        return search_associations(
            subject_category='gene',
            object_category='pathway',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

# @ns.route('/gene/<id>/expression')
# @api.doc(params={'id': 'CURIE identifier of gene, e.g. MGI:97364'})
# class GeneExpressionAssociations(Resource):
#
#     @api.expect(core_parser)
#     @api.marshal_with(association_results)
#     def get(self, id):
#         """
#         Returns expression associated with a gene
#         """
#
#         results = get_gene_to_expression(id)

@ns.route('/gene/<id>/expression/anatomy', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750. Equivalent IDs can be used with same results'})
class GeneExpressionAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns expression events for a gene
        """

        return search_associations(
            subject_category='gene',
            object_category='anatomical entity',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/anatomy', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:13434'})
class GeneAnatomyAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns anatomical entities associated with a gene
        """

        return search_associations(
            subject_category='gene',
            object_category='anatomical entity',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. ZFIN:ZDB-GENE-980526-166'})
class GeneGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes associated with a gene
        """
        return search_associations(
            subject_category='gene',
            object_category='genotype',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/function', doc=SHOW_ROUTE)
@api.doc(params={'id': 'id, e.g. NCBIGene:6469. Equivalent IDs can be used with same results'})
class GeneFunctionAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns function associations for a gene.

        IMPLEMENTATION DETAILS
        ----------------------

        Note: currently this is implemented as a query to the GO/AmiGO solr instance.
        This directly supports IDs such as:

         - ZFIN e.g. ZFIN:ZDB-GENE-050417-357

        Note that the AmiGO GOlr natively stores MGI annotations to MGI:MGI:nn. However,
        the standard for biolink is MGI:nnnn, so you should use this (will be transparently
        mapped to legacy ID)

        Additionally, for some species such as Human, GO has the annotation attached to the UniProt ID.
        Again, this should be transparently handled; e.g. you can use NCBIGene:6469, and this will be
        mapped behind the scenes for querying.
        """

        assocs = search_associations(
            object_category='function',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

        # If there are no associations for the given ID, try other IDs.
        # Note the AmiGO instance does *not* support equivalent IDs
        if len(assocs['associations']) == 0:
            # Note that GO currently uses UniProt as primary ID for some sources: https://github.com/biolink/biolink-api/issues/66
            # https://github.com/monarch-initiative/dipper/issues/461
            #sg_dev = SciGraph(url='https://scigraph-data.monarchinitiative.org/scigraph/')
            sg_dev = scigraph
            prots = sg_dev.gene_to_uniprot_proteins(id)
            for prot in prots:
                pr_assocs = search_associations(
                    object_category='function',
                    subject=prot,
                    user_agent=USER_AGENT,
                    **core_parser.parse_args()
                )
                assocs['associations'] += pr_assocs['associations']
        return assocs

@ns.route('/gene/<id>/literature', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750'})
class GeneLiteratureAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns publications associated with a gene
        """

        return search_associations(
            subject_category='gene',
            object_category='publication',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/models', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:17988'})
class GeneModelAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns models associated with a gene
        """

        return search_associations(
            subject_category='gene',
            object_category='model',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/ortholog/phenotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750'})
class GeneOrthologPhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """

        Return phenotypes associated with orthologs for a gene
        """

        return search_associations(
            fq={'subject_ortholog_closure': id},
            object_category='phenotype',
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )


@ns.route('/gene/<id>/ortholog/diseases', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. NCBIGene:4750'})
class GeneOrthologDiseaseAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Return diseases associated with orthologs of a gene
        """

        return search_associations(
            fq={'subject_ortholog_closure': id},
            object_category='disease',
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/gene/<id>/variants', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of gene, e.g. HGNC:10896'})
class GeneVariantAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns variants associated with a gene
        """
        return search_associations(
            subject_category='gene',
            object_category='variant',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/phenotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, Orphanet:1934, DOID:678. Equivalent IDs can be used with same results'})
class DiseasePhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns phenotypes associated with disease
        """
        results = search_associations(
            subject_category='disease',
            object_category='phenotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )
        fcs = results.get('facet_counts')
        if fcs:
            fcs['closure_bin'] = create_closure_bin(fcs.get('object_closure'))
        return results

@ns.route('/disease/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
class DiseaseGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a disease
        """
        return search_associations(
            subject_category='disease',
            object_category='gene',
            subject=id,
            invert_subject_object=True,
            user_agent=USER_AGENT,
            **core_parser.parse_args())


@ns.route('/disease/<id>/treatment', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. DOID:2841 (asthma). Equivalent IDs not yet supported'})
class DiseaseSubstanceAssociations(Resource):

    @api.expect(core_parser)
    #TODO: @api.marshal_list_with(association)
    def get(self, id):
        """
        Returns substances associated with a disease.

        e.g. drugs or small molecules used to treat

        """
        return condition_to_drug(id)

@ns.route('/disease/<id>/models', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
class DiseaseModelAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """Returns associations to models of the disease

        In the association object returned, the subject will be the disease, and the object will be the model.
        The model may be a gene or genetic element.

        If the query disease is a general class, the association subject may be to a specific disease.

        In some cases the association will be *direct*, for example if a paper asserts a genotype is a model of a disease.

        In other cases, the association will be *indirect*, for
        example, chaining over orthology. In these cases the chain
        will be reflected in the *evidence graph*

        * TODO: provide hook into owlsim for dynamic computation of models by similarity

        """

        return search_associations(
            subject_category='disease',
            object_category='model',
            subject=id,
            invert_subject_object=True,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/models/<taxon>', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
@api.doc(params={'taxon': 'CURIE of organism taxonomy class to constrain models, e.g NCBITaxon:10090 (M. musculus).\n\n Higher level taxa may be used'})
class DiseaseModelTaxonAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id, taxon):
        """
        Returns associations to models of the disease constrained by taxon

        See /disease/<id>/models route for full details

        """

        return search_associations(
            subject_category='disease',
            object_category='model',
            subject=id,
            invert_subject_object=True,
            object_taxon=taxon,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. Orphanet:399158, DOID:0080008. Equivalent IDs can be used with same results'})
class DiseaseGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes associated with a disease
        """

        return search_associations(
            subject_category='disease',
            object_category='genotype',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/literature', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
class DiseaseLiteratureAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns publications associated with a disease
        """

        return search_associations(
            subject_category='disease',
            object_category='publication',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/models', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
class DiseaseModelAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns models associated with a disease
        """

        # Note: ontobio automagically sets invert_subject_object when (subject,object) is (disease,model)
        return search_associations(
            subject_category='disease',
            object_category='model',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/pathways', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. DOID:4450. Equivalent IDs can be used with same results'})
class DiseasePathwayAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns pathways associated with a disease
        """

        return search_associations(
            subject_category='disease',
            object_category='pathway',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/disease/<id>/variants', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of disease, e.g. OMIM:605543, DOID:678. Equivalent IDs can be used with same results'})
class DiseaseVariantAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns variants associated with a disease
        """

        return search_associations(
            subject_category='disease',
            object_category='variant',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/phenotype/<id>/anatomy', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of phenotype, e.g. MP:0008521. Equivalent IDs can be used with same results'})
class PhenotypeAnatomyAssociations(Resource):
    # Note: This depends on https://github.com/biolink/biolink-api/issues/122
    @api.expect(core_parser)
    @api.marshal_list_with(named_object)
    def get(self, id):
        """
        Returns anatomical entities associated with a phenotype.

        Example IDs:

         * MP:0008521 abnormal Bowman membrane

        For example, *abnormal limb development* will map to *limb*
        """
        objs = scigraph.phenotype_to_entity_list(id)
        return objs

@ns.route('/phenotype/<id>/diseases', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of phenotype, e.g. HP:0007359. Equivalent IDs can be used with same results'})
class PhenotypeDiseaseAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns diseases associated with a phenotype
        """

        results = search_associations(
            subject_category='phenotype',
            object_category='disease',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )
        # fcs = results.get('facet_counts')
        # if fcs is not None:
        #     fcs['closure_bin'] = create_closure_bin(fcs.get('object_closure'))
        return results


@ns.route('/phenotype/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  WBPhenotype:0000180 (axon morphology variant), MP:0001569 (abnormal circulating bilirubin level), '})
class PhenotypeGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a phenotype

        """
        return search_associations(
            subject_category='phenotype',
            object_category='gene',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )


@ns.route('/phenotype/<id>/gene/<taxid>/ids', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  MP:0001569 (abnormal circulating bilirubin level)'})
@api.doc(params={'taxid': 'Species or high level taxon grouping, e.g  NCBITaxon:10090 (Mus musculus)'})
class PhenotypeGeneByTaxonAssociations(Resource):

    @api.expect(core_parser)
    #@api.marshal_list_with(association)
    def get(self, id, taxid):
        """
        Returns gene ids for all genes for a particular phenotype in a taxon

        For example, MP:0001569 + NCBITaxon:10090 (mouse)

        """
        return select_distinct_subjects(
            subject_category='gene',
            object_category='phenotype',
            subject_taxon=taxid,
            user_agent=USER_AGENT
        )

@ns.route('/phenotype/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  WBPhenotype:0000180 (axon morphology variant), MP:0001569 (abnormal circulating bilirubin level)'})
class PhenotypeGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes associated with a phenotype
        """

        return search_associations(
            subject_category='phenotype',
            object_category='genotype',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/phenotype/<id>/literature', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  WBPhenotype:0000180 (axon morphology variant), MP:0001569 (abnormal circulating bilirubin level)'})
class PhenotypeLieratureAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns publications associated with a phenotype
        """

        return search_associations(
            subject_category='phenotype',
            object_category='publication',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/phenotype/<id>/pathways', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  MP:0001569 (abnormal circulating bilirubin level)'})
class PhenotypePathwayAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns pathways associated with a phenotype
        """

        return search_associations(
            subject_category='phenotype',
            object_category='pathway',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/phenotype/<id>/variants', doc=SHOW_ROUTE)
@api.doc(params={'id': 'Pheno class CURIE identifier, e.g  WBPhenotype:0000180 (axon morphology variant), MP:0001569 (abnormal circulating bilirubin level)'})
class PhenotypeVariantAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns variants associated with a phenotype
        """

        return search_associations(
            subject_category='phenotype',
            object_category='variant',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@api.deprecated
@ns.route('/goterm/<id>/genes')
@api.doc(params={'id': 'CURIE identifier of a GO term, e.g. GO:0044598'})
class GotermGeneAssociations(Resource):

    @api.expect(core_parser_with_rel)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns associations to GO terms for a gene
        """
        args = core_parser_with_rel.parse_args()
        if args['relationship_type'] == ACTS_UPSTREAM_OF_OR_WITHIN:
            return search_associations(
                subject_category='gene',
                object_category='function',
                fq = {'regulates_closure': id},
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)
        elif args['relationship_type'] == INVOLVED_IN_REGULATION_OF:
            # Temporary fix until https://github.com/geneontology/amigo/pull/469
            # and https://github.com/owlcollab/owltools/issues/241 are resolved
            return search_associations(
                subject_category = 'gene',
                object_category = 'function',
                fq = {'regulates_closure': id, '-isa_partof_closure': id},
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)
        elif args['relationship_type'] == INVOLVED_IN:
            return search_associations(
                subject_category='gene',
                object_category='function',
                subject=id,
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)


@ns.route('/function/<id>/genes')
@api.doc(params={'id': 'CURIE identifier of a GO term, e.g. GO:0044598'})
class FunctionGeneAssociations(Resource):

    @api.expect(core_parser_with_rel)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated to a GO term
        """
        args = core_parser_with_rel.parse_args()
        if args['relationship_type'] == ACTS_UPSTREAM_OF_OR_WITHIN:
            return search_associations(
                subject_category='gene',
                object_category='function',
                fq = {'regulates_closure': id},
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)
        elif args['relationship_type'] == INVOLVED_IN_REGULATION_OF:
            # Temporary fix until https://github.com/geneontology/amigo/pull/469
            # and https://github.com/owlcollab/owltools/issues/241 are resolved
            return search_associations(
                subject_category = 'gene',
                object_category = 'function',
                fq = {'regulates_closure': id, '-isa_partof_closure': id},
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)
        elif args['relationship_type'] == INVOLVED_IN:
            return search_associations(
                subject_category='gene',
                object_category='function',
                subject=id,
                invert_subject_object=True,
                user_agent=USER_AGENT,
                **args)


@ns.route('/function/<id>')
@api.doc(params={'id': 'CURIE identifier of a function term (e.g. GO:0044598)'})
class FunctionAssociations(Resource):

    @api.expect(basic_parser)
    def get(self, id):
        """
        Returns annotations associated to a function term
        """

        # annotation_class,aspect
        fields = "date,assigned_by,bioentity_label,bioentity_name,synonym,taxon,taxon_label,panther_family,panther_family_label,evidence,evidence_type,reference,annotation_extension_class,annotation_extension_class_label"
        query_filters = "annotation_class%5E2&qf=annotation_class_label_searchable%5E1&qf=bioentity%5E2&qf=bioentity_label_searchable%5E1&qf=bioentity_name_searchable%5E1&qf=annotation_extension_class%5E2&qf=annotation_extension_class_label_searchable%5E1&qf=reference_searchable%5E1&qf=panther_family_searchable%5E1&qf=panther_family_label_searchable%5E1&qf=bioentity_isoform%5E1"
        args = basic_parser.parse_args()

        evidences = args['evidence']
        evidence = ""
        if evidences is not None:
            evidence = "&fq=evidence_closure:("
            for ev in evidences:
                evidence += "\"" + ev + "\","
            evidence = evidence[:-1]
            evidence += ")"

        taxon_restrictions = ""
        cfg = get_config()
        if cfg.taxon_restriction is not None:
            taxon_restrictions = "&fq=taxon_subset_closure:("
            for c in cfg.taxon_restriction:
                taxon_restrictions += "\"" + c + "\","
            taxon_restrictions = taxon_restrictions[:-1]
            taxon_restrictions += ")"


        optionals = "&defType=edismax&start=" + str(args['start']) + "&rows=" + str(args['rows']) + evidence + taxon_restrictions
        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ANNOTATION, id, query_filters, fields, optionals)
        
        return data


@ns.route('/function/<id>/taxons')
@api.doc(params={'id': 'CURIE identifier of a GO term, e.g. GO:0044598'})
class FunctionTaxonAssociations(Resource):

    @api.expect(basic_parser)
    def get(self, id):
        """
        Returns taxons associated to a GO term
        """

        fields = "taxon,taxon_label"
        query_filters = "annotation_class%5E2&qf=annotation_class_label_searchable%5E1&qf=bioentity%5E2&qf=bioentity_label_searchable%5E1&qf=bioentity_name_searchable%5E1&qf=annotation_extension_class%5E2&qf=annotation_extension_class_label_searchable%5E1&qf=reference_searchable%5E1&qf=panther_family_searchable%5E1&qf=panther_family_label_searchable%5E1&qf=bioentity_isoform%5E1"
        args = basic_parser.parse_args()

        evidences = args['evidence']
        evidence = ""
        if evidences is not None:
            evidence = "&fq=evidence_closure:("
            for ev in evidences:
                evidence += "\"" + ev + "\","
            evidence = evidence[:-1]
            evidence += ")"

        taxon_restrictions = ""
        cfg = get_config()
        if cfg.taxon_restriction is not None:
            taxon_restrictions = "&fq=taxon_subset_closure:("
            for c in cfg.taxon_restriction:
                taxon_restrictions += "\"" + c + "\","
            taxon_restrictions = taxon_restrictions[:-1]
            taxon_restrictions += ")"
        

        optionals = "&defType=edismax&start=" + str(args['start']) + "&rows=" + str(args['rows']) + evidence + taxon_restrictions
        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ANNOTATION, id, query_filters, fields, optionals)
        
        return data


@ns.route('/function/<id>/literature')
@api.doc(params={'id': 'CURIE identifier of a GO term, e.g. GO:0044598'})
class FunctionLiteratureAssociations(Resource):

    @api.expect(basic_parser)
    def get(self, id):
        """
        Returns publications associated to a GO term
        """

        fields = "reference"
        query_filters = "annotation_class%5E2&qf=annotation_class_label_searchable%5E1&qf=bioentity%5E2&qf=bioentity_label_searchable%5E1&qf=bioentity_name_searchable%5E1&qf=annotation_extension_class%5E2&qf=annotation_extension_class_label_searchable%5E1&qf=reference_searchable%5E1&qf=panther_family_searchable%5E1&qf=panther_family_label_searchable%5E1&qf=bioentity_isoform%5E1"
        args = basic_parser.parse_args()

        evidences = args['evidence']
        evidence = ""
        if evidences is not None:
            evidence = "&fq=evidence_closure:("
            for ev in evidences:
                evidence += "\"" + ev + "\","
            evidence = evidence[:-1]
            evidence += ")"

        taxon_restrictions = ""
        cfg = get_config()
        if cfg.taxon_restriction is not None:
            taxon_restrictions = "&fq=taxon_subset_closure:("
            for c in cfg.taxon_restriction:
                taxon_restrictions += "\"" + c + "\","
            taxon_restrictions = taxon_restrictions[:-1]
            taxon_restrictions += ")"


        optionals = "&defType=edismax&start=" + str(args['start']) + "&rows=" + str(args['rows']) + evidence + taxon_restrictions
        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ANNOTATION, id, query_filters, fields, optionals)
        
        list = []
        for elt in data:
            for ref in elt['reference']:
                list.append(ref)

        return { "references": list }



@ns.route('/pathway/<id>/genes')
@api.doc(params={'id': 'CURIE any pathway element. E.g. REACT:R-HSA-5387390'})
class PathwayGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a pathway
        """

        return search_associations(
            subject_category='gene',
            object_category='pathway',
            object=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/anatomy/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of anatomical entity, e.g. GO:0005634 (nucleus), UBERON:0002037 (cerebellum), CL:0000540 (neuron). Equivalent IDs can be used with same results'})
class AnatomyGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a given anatomy
        """

        return search_associations(
            subject_category='gene',
            object_category='anatomical entity',
            object=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/anatomy/<id>/genes/<taxid>', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of anatomical entity, e.g. GO:0005634 (nucleus), UBERON:0002037 (cerebellum), CL:0000540 (neuron). Equivalent IDs can be used with same results'})
@api.doc(params={'taxid': 'Species or high level taxon grouping, e.g  NCBITaxon:10090 (Mus musculus)'})
class AnatomyGeneByTaxonAssociations(Resource):

    @api.expect(core_parser)
    #@api.marshal_list_with(association)
    def get(self, id, taxid):
        """
        Returns gene ids for all genes for a particular anatomy in a taxon

        For example, + NCBITaxon:10090 (mouse)

        """
        return search_associations(
            subject_category='gene',
            object_category='anatomical entity',
            subject_taxon=taxid,
            object=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/substance/<id>/roles', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of substance, e.g. CHEBI:40036'})
class SubstanceRoleAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_list_with(association)
    def get(self, id):
        """
        Returns associations between given drug and roles

        Roles may be human-oriented (e.g. pesticide) or molecular (e.g. enzyme inhibitor)
        """
        return scigraph.substance_to_role_associations(id)

@ns.route('/substance/<id>/participant_in', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of substance, e.g. CHEBI:40036'})
class SubstanceParticipantInAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_list_with(association)
    def get(self, id):
        """
        Returns associations between an activity and process and the specified substance

        Examples relationships:

         * substance is a metabolite of a process
         * substance is synthesized by a process
         * substance is modified by an activity
         * substance elicits a response program/pathway
         * substance is transported by activity or pathway

        For example, CHEBI:40036 (amitrole)

        """
        return scigraph.substance_participates_in_associations(id)


@ns.route('/substance/<id>/treats', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of substance, e.g. CHEBI:40036'})
class SubstanceTreatsAssociations(Resource):

    @api.expect(core_parser)
    #TODO: @api.marshal_list_with(association)
    def get(self, id):
        """
        Returns substances associated with a disease.

        e.g. drugs or small molecules used to treat

        """
        return condition_to_drug(id)

@ns.route('/genotype/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of genotype, e.g. ZFIN:ZDB-FISH-150901-6607'})
class GenotypeGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes-genotype associations.

        Genotypes may be related to one another according to the GENO model
        """

        # TODO: invert
        return search_associations(
            subject_category='genotype',
            object_category='genotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/genotype/<id>/phenotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of genotype, e.g. ZFIN:ZDB-FISH-150901-4286'})
class GenotypePhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns phenotypes associated with a genotype
        """

        return search_associations(
            subject_category='genotype',
            object_category='phenotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/genotype/<id>/diseases', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of genotype, e.g. dbSNPIndividual:11441 (if non-human will return models)'})
class GenotypeDiseaseAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns diseases associated with a genotype
        """

        # TODO: invert
        return search_associations(
            subject_category='genotype',
            object_category='disease',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/genotype/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of genotype, e.g. ZFIN:ZDB-FISH-150901-6607'})
class GenotypeGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a genotype
        """

        # TODO: invert
        return search_associations(
            subject_category='genotype',
            object_category='gene',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

##

@ns.route('/variant/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of variant, e.g. ZFIN:ZDB-ALT-010427-8'})
class VariantGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes associated with a variant
        """

        # TODO: invert
        return search_associations(
            subject_category='variant',
            object_category='genotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/variant/<id>/phenotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of variant, e.g. ZFIN:ZDB-ALT-010427-8, ClinVarVariant:39783'})
class VariantPhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns phenotypes associated with a variant
        """

        return search_associations(
            subject_category='variant',
            object_category='phenotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/variant/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier of variant, e.g. ZFIN:ZDB-ALT-010427-8, ClinVarVariant:39783'})
class VariantGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a variant
        """

        # TODO: invert
        return search_associations(
            subject_category='variant',
            object_category='gene',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/diseases', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier for a model, e.g. MGI:5573196'})
class ModelDiseaseAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns diseases associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='disease',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/genes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier for a model, e.g. MMRRC:042787'})
class ModelGeneAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genes associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='gene',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/genotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier for a model, e.g. Coriell:NA16660'})
class ModelGenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns genotypes associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='genotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/literature', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier for a model, e.g. MGI:5644542'})
class ModelLiteratureAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns publications associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='publication',
            invert_subject_object=True,
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/phenotypes', doc=SHOW_ROUTE)
@api.doc(params={'id': 'id'})
class ModelPhenotypeAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns phenotypes associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='phenotype',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )

@ns.route('/model/<id>/variants', doc=SHOW_ROUTE)
@api.doc(params={'id': 'CURIE identifier for a model, e.g. MMRRC:042787'})
class ModelVariantAssociations(Resource):

    @api.expect(core_parser)
    @api.marshal_with(association_results)
    def get(self, id):
        """
        Returns variants associated with a model
        """

        return search_associations(
            subject_category='model',
            object_category='variant',
            subject=id,
            user_agent=USER_AGENT,
            **core_parser.parse_args()
        )
