"""Controlled offline semantics fixtures; never write research observations."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec = importlib.util.spec_from_file_location('semantics', Path(__file__).resolve().parents[2] / 'scripts/resolve_hydrology_semantics.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


@pytest.mark.parametrize('definition,status', [('msl','nwdp_datum_verified_msl'),
    ('gauge','nwdp_datum_verified_gauge'), ('station_specific','nwdp_datum_station_specific')])
def test_datum_requires_exact_field_citation(definition, status):
    assert s.datum_status(definition, exact_resource=True, citation='official dictionary') == status
    assert s.datum_status(definition, citation='general handbook') == 'nwdp_datum_unresolved'
    assert s.datum_status(definition, exact_resource=True) == 'nwdp_datum_unresolved'


@pytest.mark.parametrize('definition', ['525.1600', '536.00', 'meter', 'MeanSeaLevel', 'RL_of_zeroGauge', None])
def test_no_datum_inference_from_values_or_auxiliary_names(definition):
    assert s.datum_status(definition) == 'nwdp_datum_unresolved'


def test_unknown_datum_definition_rejected():
    with pytest.raises(ValueError): s.datum_status('height', exact_resource=True, citation='official')


@pytest.mark.parametrize('first,second,citations,expected', [('msl','msl',True,'datum_compatible'),
    ('msl','gauge',True,'datum_incompatible'), ('msl','msl',False,'datum_unresolved'),
    (None,'msl',True,'datum_unresolved')])
def test_threshold_gate(first, second, citations, expected):
    assert s.threshold_status(first, second, citations=citations) == expected


@pytest.mark.parametrize('status', sorted(s.LINEAGE))
def test_lineage_vocabulary_and_record_evidence(status):
    assert s.lineage_status(record_evidence=status, citation='official record') == status
    with pytest.raises(ValueError): s.lineage_status(record_evidence=status)


def test_revision_possibility_does_not_select_either_source():
    cases = [{'station_id':'fixture', 'classification':'source_value_conflict', 'nwdp_value':'4', 'book_value':'5'},
             {'station_id':'fixture', 'classification':'yearbook_computed_vs_nwdp', 'nwdp_value':'6', 'book_value':'7'},
             {'station_id':'fixture', 'classification':'exact'}]
    before = deepcopy(cases)
    result = s.lineage_rows(cases, s.lineage_status(revision_procedure=True))
    assert len(result) == 2 and cases == before
    for original, current in zip(cases, result):
        assert all(current[k] == v for k,v in original.items())
        assert current['preferred_for_analysis'] is None and current['preference_basis'] is None
        assert current['record_revision_evidence'] is None
    assert s.lineage_status() == 'lineage_unresolved'
    with pytest.raises(ValueError): s.lineage_rows(cases, 'NWDP_is_newer')


def test_coordinate_parsing_precision_and_no_averaging():
    text = 'Station fixture\n1.23456 72.123 123 HO/FF FIXTURE01\n'
    result = s.parse_coordinate_row(text, 'FIXTURE01')
    assert result['latitude_original'] == '1.23456'
    assert result['longitude_original'] == '72.123'
    assert result['precision_decimal_places'] == [5,3]
    assert result['latitude'] == 1.23456 and result['longitude'] == 72.123
    assert s.coordinate_status() == 'coordinate_conflict_unresolved'
    assert s.coordinate_status(precision_only=True) == 'coordinate_precision_difference_likely'
    assert s.coordinate_status(explicit_explanation='documented correction', citation='official') == 'coordinate_variation_explained'
    with pytest.raises(ValueError): s.coordinate_status(relocation_claim=True)
    with pytest.raises(ValueError): s.coordinate_status(explicit_explanation='guess', relocation_claim=True)


@pytest.mark.parametrize('text', ['absent', '91.1 72.1 12 HO CODE', '1.1 72.1 12 HO CODE\n1.2 72.2 12 HO CODE'])
def test_bad_or_ambiguous_coordinate_history(text):
    with pytest.raises(ValueError): s.parse_coordinate_row(text, 'CODE')


@pytest.mark.parametrize('kwargs,expected', [({},'policy_conflict_unresolved'),
    ({'attributed_permission':True},'reuse_clearly_permitted_with_attribution'),
    ({'producer_permission':True},'producer_permission_required'),
    ({'internal_permission':True},'reuse_permitted_for_internal_research_only'),
    ({'attributed_permission':True,'applicability_ambiguous':True},'policy_conflict_unresolved')])
def test_reuse_does_not_invent_standard_licence(kwargs, expected):
    assert s.reuse_status(**kwargs) == expected


def test_readiness_no_absolute_datum_or_eligibility_expansion():
    kwargs = dict(identity_strong=True, consistent_units=True, unique_times=True,
                  reference_stability_verified=False, time_semantics_verified=False)
    assert s.change_readiness(**kwargs).startswith('conditional_future')
    for key in ['identity_strong','consistent_units','unique_times']:
        assert s.change_readiness(**{**kwargs,key:False}) == 'blocked'
    assert s.change_readiness(**{**kwargs,'reference_stability_verified':True,'time_semantics_verified':True}) == 'usable_only_for_within_station_change_rate'
    assert s.discharge_readiness(0) == 'blocked'
    assert s.discharge_readiness(2) == 'restricted_to_currently_eligible_14_rows'


def test_clarification_contains_precise_questions_but_never_sends():
    metadata = {'dataset_id':'dataset_fixture','resource_id':'resource_fixture','title':'fixture resource','download_url':'https://official.example/fixture'}
    identities = [{'station_id':'fixture'}]; cases = [{'station_id':'fixture','classification':'source_value_conflict'}]
    before = deepcopy((metadata, identities, cases))
    package = s.clarification(metadata, identities, cases)
    assert package['status'] == 'prepared_not_sent' and package['no_message_sent']
    assert set(package['questions']) == {'datum','lineage','quality','coordinates','reuse'}
    assert (metadata, identities, cases) == before
    assert package == s.clarification(metadata, identities, cases)


def test_resource_metadata_preserves_units_timestamps_not_revision_or_datum():
    source = {'schema_and_census': {'original_columns':['Water Level (meter)', 'RL_of_zeroGauge'], 'quality_columns':[]}}
    resource = dict(id=s.RESOURCE, name='fixture Krishna hourly', description='fixture', format='CSV',
                    created='2025-02-20', last_modified='2025-02-20', metadata_modified='2025-04-30',
                    hash='fixture_md5', size=123, url='https://official.example/download')
    dataset = dict(id=s.DATASET, author='CWC', resources=[resource], metadata_modified='2026-10-07',
                   license_title='Other (Open)', extras=[{'key':'Unit','value':'m'}])
    catalogue = {'result':{'results':[dataset]}}
    before = deepcopy((catalogue,source))
    metadata = s.resource_metadata(catalogue,source)
    assert (catalogue,source) == before
    assert metadata['record_revision_fields'] == []
    assert not metadata['timestamps_are_record_revision_dates']
    assert metadata['licence_url'] is None
    assert metadata['original_columns'] == source['schema_and_census']['original_columns']
    assert s.datum_status() == 'nwdp_datum_unresolved'
    dataset['id'] = 'wrong'
    with pytest.raises(ValueError,match='dataset'): s.resource_metadata(catalogue,source)


def test_preservation_all_1697_values_81_cases_14_eligible():
    observations = [{'original_value':str(i),'original_time':f'fixture-{i}'} for i in range(1697)]
    quality = [{**r,'analysis_eligibility':'eligible_with_quality_caveat' if i<14 else 'retain_not_use_for_features'} for i,r in enumerate(observations)]
    cases = [{} for _ in range(81)]
    before = deepcopy((observations, quality, cases))
    s.preserve_prior(observations, quality, cases)
    assert (observations, quality, cases) == before
    for i in range(1697): assert observations[i]['original_value'] == str(i)
    quality[900]['original_value'] = 'corrupted'
    with pytest.raises(ValueError,match='Source values'): s.preserve_prior(observations, quality, cases)
    quality = deepcopy(before[1]); quality[14]['analysis_eligibility'] = 'eligible_with_quality_caveat'
    with pytest.raises(ValueError,match='Eligibility'): s.preserve_prior(observations, quality, cases)
    with pytest.raises(ValueError,match='counts'): s.preserve_prior(observations, before[1], cases[:-1])


def test_immutable_build_readonly_validation_bytes_hash_size_mtime(tmp_path, monkeypatch):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root = Path(folder); code = root/'code.py'; code.write_text('fixture')
        original = root/'source.json'; original.write_bytes(b'{"fixture": true}\r\n')
        monkeypatch.setattr(s,'ROOT',root); monkeypatch.setattr(s,'__file__',str(code))
        monkeypatch.setattr(s,'inputs',lambda:[s.record(original)])
        artifacts = {'fixture.json':s.body({'controlled_fixture':True})}
        monkeypatch.setattr(s,'assemble',lambda:(artifacts,{'source_values_changed':0}))
        output = root/'new_version'; s.freeze(output)
        protected = [original,code,*output.iterdir()]
        before = {p:(p.read_bytes(),s.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in protected}
        s.validate(output); s.validate(output)
        assert before == {p:(p.read_bytes(),s.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in protected}
        with pytest.raises(ValueError,match='Immutable'): s.freeze(output)
        assert before == {p:(p.read_bytes(),s.digest(p),p.stat().st_size,p.stat().st_mtime_ns) for p in protected}
        (output/'fixture.json').write_text('corrupt')
        with pytest.raises(ValueError,match='reproduction'): s.validate(output)
