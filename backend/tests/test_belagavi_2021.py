"""One2021anchor; controlled metadata/arrays and temporary files, no live services."""
from copy import deepcopy
from datetime import datetime,timezone
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
from shapely.geometry import box,mapping,shape

SPEC=importlib.util.spec_from_file_location('belagavi2021',Path(__file__).resolve().parents[2]/'scripts/evaluate_belagavi_2021.py')
e=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(e)


def claims():
    return {'event_id':e.EVENT,'primary':{'listing_date':'2021-07-29','issue_date':'2021-07-29',
            'acquisition_date':'2021-07-26','sensor':'WorldView-3','localities':['Hulagabali','Halyal']},
            'corroborating_map':{'acquisition_date':'2021-07-28','sensor':'Resourcesat-2A LISS-III','localities':['Kudachi']},
            'reference_status':'official_map_reference_available',
            'contextual_observation_bracket':{'start':'2021-07-26','end_inclusive':'2021-07-28','status':'derived_bracket_between_two_official_observations_not_daily_flood_labels'}}


def location():return {'type':'node','id':2548417075,'lon':74.995,'lat':16.661,'tags':{'name':'Hulagabali','place':'village'}}


def scene(day,orbit=107,platform='A',pass_='DESCENDING',coverage=1):
    index=day+str(orbit)+platform
    return {'id':e.p.SOURCE+'/'+index,'footprint':mapping(box(74,16,76,18)),
     'analysis_window_coverage_fraction':coverage,'aoi_coverage_fractions':dict.fromkeys(['1','2','3','4'],coverage),
     'aoi_intersection_areas_m2':dict.fromkeys(['1','2','3','4'],coverage*100),
     'aoi_areas_m2':dict.fromkeys(['1','2','3','4'],100),
     'properties':{'system:index':index,'system:time_start':int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000),
      'instrumentMode':'IW','resolution':'H','resolution_meters':10,'transmitterReceiverPolarisation':['VV','VH'],
      'orbitProperties_pass':pass_,'relativeOrbitNumber_start':orbit,'platform_number':platform}}


def test_listing_issue_and_acquisition_are_separate_and_original_unchanged():
    c=claims();before=deepcopy(c);assert e.validate_anchor(c)==before and c==before
    assert c['primary']['acquisition_date']!=c['primary']['listing_date']


@pytest.mark.parametrize('key,value',[('acquisition_date','2021-07-29'),('sensor','Sentinel-1'),('issue_date','2021-07-26')])
def test_filename_or_listing_cannot_substitute_observation(key,value):
    c=claims();c['primary'][key]=value
    with pytest.raises(ValueError):e.validate_anchor(c)


@pytest.mark.parametrize('field',['flood_polygon','digitized_pdf_extent','pixel_ground_truth'])
def test_no_manual_pdf_flood_reference(field):
    c=claims();c[field]={}
    with pytest.raises(ValueError):e.validate_anchor(c)


def test_embedded_geopdf_registration_is_coverage_not_flood_geometry():
    with TemporaryDirectory() as tmp:
        pdf=Path(tmp)/'fixture.pdf';pdf.write_bytes(b'%PDF-1.6\n1 0 obj <</Type /Page /VP[<</Type/Viewport/BBox[0 0 1 1]/Name (Postflood)/Measure 2 0 R >>]>> endobj\n2 0 obj <</Subtype/GEO/GPTS[16 74 17 74 17 75 16 75]/GCS 3 0 R>> endobj\n3 0 obj <</WKT(fixture)>> endobj')
        result=e.geospatial_viewports(pdf)
        assert result[0]['geographic_bounds']==[74,16,75,17]
        assert result[0]['interpretation']=='Source-provided map viewport registration, not inundation geometry'


def test_missing_or_unsupported_pdf_registration_fails_closed():
    with TemporaryDirectory() as tmp:
        p=Path(tmp)/'fixture.pdf';p.write_bytes(b'%PDF-1.6\nNo geographic dictionaries')
        with pytest.raises(ValueError):e.geospatial_viewports(p)


def test_nested_aoi_levels_public_coordinate_area_and_determinism():
    rows=e.aoi_plan(location());assert rows==e.aoi_plan(location())
    assert [r['side_m'] for r in rows]==[2000,25000,90000,180000]
    for i,r in enumerate(rows):
        assert r['scope_type']=='retrieval_window_not_official_flood_boundary' and r['area_m2_projected']==r['side_m']**2
        assert shape(r['public_geometry']).is_valid
        if i:assert shape(rows[i]['public_geometry']).covers(shape(rows[i-1]['public_geometry']))


def test_wrong_locality_not_guessed():
    loc=location();loc['tags']['name']='unknown'
    with pytest.raises(ValueError):e.aoi_plan(loc)


def test_unfiltered_availability_not_confused_with_zero_vh_filter():
    r=scene('2021-07-26');r['properties']['transmitterReceiverPolarisation']=['VV']
    counts=e.filter_attrition([r]);assert counts['unfiltered']==counts['IW']==counts['IW_VV']==1
    assert counts['IW_VH']==counts['IW_VV_VH']==0
    assert e.group_inventory([r])['status']=='sentinel1_pair_unavailable'


def test_filter_attrition_separate_pass_orbit_platform_branches():
    scenes=[scene('2021-07-14'),scene('2021-07-26',orbit=34,platform='B',pass_='ASCENDING')]
    counts=e.filter_attrition(scenes);assert counts['ascending']==counts['descending']==1
    assert counts['relative_orbits']=={'107':1,'34':1} and counts['platforms']=={'A':1,'B':1}


def test_numeric_ee_histogram_keys_normalize_without_rewriting_source():
    counts=e.filter_attrition([scene('2021-07-26')]);counts['relative_orbits']={'107.0':1};before=deepcopy(counts)
    assert e.normalize_histogram_keys(counts)['relative_orbits']=={'107':1} and counts==before
    counts['relative_orbits']['107']=1
    with pytest.raises(ValueError):e.normalize_histogram_keys(counts)


@pytest.mark.parametrize('kwargs',[{'orbit':34},{'platform':'B'},{'pass_':'ASCENDING'},{'coverage':0}])
def test_homogeneous_group_cannot_mix_orbits_platforms_passes_or_missing_swath(kwargs):
    assert e.group_inventory([scene('2021-07-14'),scene('2021-07-26',**kwargs)])['status']=='sentinel1_pair_unavailable'


def test_exact_date_priority_and_two_baselines_no_thresholds():
    rows=[scene('2021-07-02'),scene('2021-07-14'),scene('2021-07-26'),scene('2021-08-01')]
    g=e.group_inventory(rows);assert g==e.group_inventory(list(reversed(rows)))
    assert g['status']=='sentinel1_pair_available' and g['selected']['temporal_role']=='same_day_as_official_spatial_observation'
    assert len(g['selected']['baseline'])==2 and e.METHOD['threshold_analysis_performed'] is False and e.METHOD['flood_label'] is None
    grid=e.diagnostic_plan(location(),g['selected']);assert grid['bands']==13 and grid['maximum_safe_partition_workload']==162500


@pytest.mark.parametrize('day,expected',[('2021-07-25','pre_event_baseline'),('2021-07-26','same_day_as_official_spatial_observation'),
 ('2021-07-28','during_documented_observation_bracket'),('2021-08-02','shortly_after_event'),('2021-08-15','temporally_unsuitable')])
def test_temporal_classification_not_listing_date(day,expected):assert e.role(scene(day))==expected


def test_coverage_failure_is_inconclusive_not_observed_zero():
    assert e.coverage_decision(error=TimeoutError())=='sentinel1_coverage_query_inconclusive'
    assert e.coverage_decision(e.group_inventory([]))=='sentinel1_pair_unavailable'
    with pytest.raises(ValueError):e.coverage_decision()


def test_footprint_relation_not_flood_or_pixel_mask():
    plan=e.aoi_plan(location())[0];r=scene('2021-07-26');assert e.footprint_relation(r,plan)['covers'] is True
    r['footprint']=mapping(box(72,12,73,13));assert e.footprint_relation(r,plan)['intersects'] is False


def test_area_fraction_cannot_mix_geodesic_and_projected_denominators():
    spherical=4016751.6600644286
    assert e.area_fraction(spherical,spherical)==1
    with pytest.raises(ValueError):e.area_fraction(spherical,4000000)


def test_source_inventory_identity_duplicates_and_date_checks():
    r=scene('2021-07-26');e.validate_inventory([r])
    with pytest.raises(ValueError):e.validate_inventory([r,r])
    r['properties']['system:index']='wrong'
    with pytest.raises(ValueError):e.validate_inventory([r])


def test_ifi_no_forced_match_or_changed_dates():
    row={'ifi_source_event_id':'fixture','source_row_ordinal':1,'parsed_start_date':'2021-07-26','parsed_end_date_inclusive':'2021-07-28',
      'source_start_date':'literal-start','source_end_date':'literal-end','source_districts':'Belagavi',
      'source_district_lgd_codes':'source-only','source_duration_days':'1'}
    original=deepcopy(row);out=e.associate_ifi([row],claims());assert row==original and out['status']=='ambiguous'
    assert out['primary_anchor_changed'] is False and out['records'][0]['source_lgd_token']=='source-only'
    assert e.associate_ifi([],claims())['status']=='none'


def test_jrc_absence_never_invalidates_sar_or_becomes_permanent_water():
    pair={'baseline':[scene('2021-07-14')],'event_scene':scene('2021-07-26')}
    ids,names=e.band_names(pair);a=np.ones((len(names),200,200),dtype='float32');d=dict(zip(names,a))
    d['monthly_mask'][:]=0;d['yearly_mask'][:]=0;d['monthly'][:]=e.p.NODATA;d['yearly'][:]=e.p.NODATA
    r=e.continuous(a,names)[0]
    assert r['sar_valid_cells']==40000 and r['permanent_water_status_unknown_cells']==40000
    assert r['permanent_water_cells']==0 and r['threshold_sensitivity']==[]
    assert r['flood_label'] is None


def test_adjacent_same_pass_frames_not_two_independent_baselines():
    a=scene('2021-07-14');b=deepcopy(a);b['properties']['system:time_start']+=25000
    b['id']+='other-frame';b['properties']['system:index']+='other-frame'
    out=e.group_inventory([a,b,scene('2021-07-26')])
    assert len(out['selected']['baseline'])==1


def test_continuous_output_georeferenced_temp_only_and_read_only_inputs():
    import rasterio
    pair={'baseline':[scene('2021-07-14')],'event_scene':scene('2021-07-26')}
    ids,names=e.band_names(pair);values=np.ones((len(names),200,200),dtype='float32');original=values.copy()
    with TemporaryDirectory() as tmp:
        path=Path(tmp)/'continuous.tif';grid=e.diagnostic_plan(location(),pair)
        result=e.write_continuous(path,values,names,grid);e.ensure_no_labels(result)
        with rasterio.open(path) as r:
            assert str(r.crs)=='EPSG:32643' and r.count==15 and 'change_VV_dB' in r.descriptions
            assert (r.read(r.descriptions.index('change_VV_dB')+1)==0).all()
        assert np.array_equal(values,original)
        with pytest.raises(ValueError):e.write_continuous(path,values,names,grid)


@pytest.mark.parametrize('change',[{'flood_label':1},{'threshold_analysis_performed':True},{'candidate_cells':1},{'daily_flood_label':0}])
def test_no_thresholds_or_binary_labels(change):
    ids,names=e.band_names({'baseline':[scene('2021-07-14')],'event_scene':scene('2021-07-26')})
    r=e.continuous(np.ones((len(names),200,200),dtype='float32'),names)[0];r.update(change)
    with pytest.raises(ValueError):e.ensure_no_labels(r)


def test_independent_scalar_checks_preserve_values_and_original_range():
    ids,names=e.band_names({'baseline':[scene('2021-07-14')],'event_scene':scene('2021-07-26')})
    values=np.ones((len(names),200,200),dtype='float32');d=dict(zip(names,values))
    d['s0_angle'][:]=45.6;d['s1_angle'][:]=45.61;original=values.copy()
    checks=e.independent_checks(values,names)
    assert checks['all_valid_cells_checked']==40000
    assert checks['within_legacy_30_45_degree_range_cells']==0 and checks['angle_difference_within_predeclared_one_degree_cells']==40000
    assert np.array_equal(values,original) and checks['thresholds_changed'] is False


def test_freeze_refuses_existing_version_before_provider_or_source_reads():
    with TemporaryDirectory() as tmp:
        out=Path(tmp)/'out';out.mkdir();f=out/'original';f.write_bytes(b'protected\r\n')
        before={**e.p.source.fingerprint(f),'mtime_ns':f.stat().st_mtime_ns}
        with pytest.raises(ValueError,match='immutable'):e.freeze(out,Path(tmp)/'ref')
        assert before=={**e.p.source.fingerprint(f),'mtime_ns':f.stat().st_mtime_ns}


def test_completed_cache_resumes_offline_with_deterministic_provenance(monkeypatch):
    with TemporaryDirectory() as tmp:
        root=Path(tmp);raw=root/'raw';sources=root/'sources';raw.mkdir();sources.mkdir()
        monkeypatch.setattr(e,'SOURCES',sources);monkeypatch.setattr(e.p,'IFI',root/'ifi.json')
        rows=[scene('2021-07-14'),scene('2021-07-26')]
        files={sources/'official_claims.json':claims(),sources/'hulagabali_osm.json':{'elements':[location()]},
               root/'ifi.json':[],raw/'scene_inventory_response.json':rows,raw/'filter_attrition_response.json':e.filter_attrition(rows)}
        for plan in e.aoi_plan(location()):files[raw/f'aoi{plan["level"]}.json']={'plan':plan,'response':{'count':2},'retrieved_at':'fixture'}
        for path,value in files.items():e.p.source.write_new(path,value)
        def snapshot():return {str(p):{**e.p.source.fingerprint(p),'mtime_ns':p.stat().st_mtime_ns} for p in files}
        before=snapshot();a=e.assemble_metadata(raw);b=e.assemble_metadata(raw)
        a.pop('retrieved_at');b.pop('retrieved_at');assert a==b and snapshot()==before
        assert e.p.source.packed(a)==e.p.source.packed(dict(reversed(list(a.items()))))
        monkeypatch.setattr(e.p.bounded,'TimedEE',lambda *args:pytest.fail('Offline resume must not initialize a provider'))
        e.metadata(raw);assert snapshot()==before and (raw/'metadata.json').exists()
        with pytest.raises(ValueError,match='immutable'):e.metadata(raw)
