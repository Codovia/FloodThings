"""Stage5 offline prediction-time methodology. No observations/features/labels/model fitting.

Build a separate immutable review; read-only validation reproduces every artifact.
Source content is human reviewed with original public HTML and receipts retained.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html import unescape
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/reference/stage5_v1'
OUTPUT=ROOT/'data/working/karnataka_prediction_methodology_v1'
PUBLIC=ROOT/'data/reference/karnataka_prediction_methodology_v1/manifest.json'
CLASSES={'STATIC','OBSERVED_PAST','FORECAST','MODELLED_PAST','RETROSPECTIVE_ONLY','DESCRIPTIVE_ONLY','TARGET_OR_LABEL','UNRESOLVED','EXCLUDED'}
PARITY={'EXACT','COMPATIBLE_WITH_CAVEATS','PROXY_REQUIRES_VALIDATION','NO_OPERATIONAL_EQUIVALENT','UNRESOLVED'}
AVAILABILITY={'historically_available','retrospectively_available','near_real_time_available','forecast_available','prediction_time_unavailable','unresolved'}
SETS={'SAFE_NOW','SAFE_AFTER_VALIDATION','RESEARCH_ONLY','PROHIBITED'}
FORBIDDEN={'event_rainfall','gokak_discharge','future_discharge_peak','post_event_sar','reported_ifi_event',
           'gfd_extent','observed_zero','missing_as_negative','water_level_threshold','cwc_model_skill','invented_drain_capacity'}


def require(ok,message):
    if not ok:raise ValueError(message)


def read(path):return json.loads(Path(path).read_bytes())


def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def record(path):
    p=Path(path);return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}


def plain(text):
    return re.sub(r'\s+',' ',unescape(re.sub('<[^>]*>',' ',re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',text,flags=re.S|re.I))))


def sources():
    rows=[]
    for finding in read(RAW/'review_findings.json'):
        p=RAW/(finding['id']+'.html'); receipt=read(Path(str(p)+'.json'))
        require(receipt['status']=='retrieved' and receipt['http_status']=='200' and receipt['sha256']==sha(p)
                and receipt['bytes']==p.stat().st_size,'Original documentation integrity failed')
        require(urlparse(receipt['url']).scheme=='https' and all(finding[k] for k in ('title','publisher','version','section','finding','confidence')),'Incomplete primary source provenance')
        rows.append({**finding,**record(p),'url':receipt['url'],'retrieved_at':receipt['retrieved_at'],
                     'verification':'live_document_retrieved; no source observations retrieved'})
    require(len(rows)==20 and len({r['id'] for r in rows})==20,'Exact reviewed documentation scope required')
    checks={'chirps_faq':['third week','following month','pentad'], 'chirps_producer':['December 2026'],
            'glofas_history':['consolidated','monthly','v5.0'], 'glofas_forecast':['v4.0','30 days'],
            'glofas_v5_status':['pre-operational','Version 4'], 'om_history':['5 days delay','ERA5'],
            'om_single':['2024-03-14','2026-04-02'],'om_forecast':['precipitation','current conditions'],
            'dem_catalogue':['Surface Model','EGM2008'],'worldcover_catalogue':['2021','CC-BY-4.0']}
    for name,tokens in checks.items():
        body=plain((RAW/(name+'.html')).read_text()).lower()
        require(all(t.lower() in body for t in tokens),'Reviewed source meaning changed: '+name)
    return rows


def candidate(fid,name,source,kind,units,spatial,temporal,coverage,category,availability,parity,group,reason,
              *,operational=None,latency='record-level publication latency unverified',licence='source-specific terms; repository review required',
              historical='Retained research evidence; exact as-of availability unverified',quality='',deployment=False,evidence=None):
    row=dict(feature_id=fid,feature_name=name,source=source,source_type=kind,units=units,spatial_resolution=spatial,
       temporal_resolution=temporal,historical_availability=historical,prediction_time_availability=availability,
       operational_source=operational,latency=latency,feature_class=category,
       leakage_status='leakage_prohibited' if category in {'DESCRIPTIVE_ONLY','TARGET_OR_LABEL','EXCLUDED'} else
                      'requires_asof_and_vintage_checks' if availability in {'near_real_time_available','forecast_available','historically_available'} else 'availability_unverified',
       training_serving_parity=parity,licence=licence,geographic_coverage=coverage,quality_caveat=quality or reason,
       allowed_for_training=False,allowed_for_deployment=deployment,
       deployment_scope='dated_research_context_only' if deployment else 'not_approved',safe_set=group,
       scientific_candidate_only=True,reason=reason,evidence_ids=evidence or [source])
    validate_candidate(row);return row


def validate_candidate(row):
    required={'feature_id','feature_name','source','source_type','units','spatial_resolution','temporal_resolution',
        'historical_availability','prediction_time_availability','operational_source','latency','feature_class',
        'leakage_status','training_serving_parity','licence','geographic_coverage','quality_caveat',
        'allowed_for_training','allowed_for_deployment','reason','safe_set','evidence_ids'}
    require(required<=set(row),'Candidate schema incomplete')
    require(row['feature_class'] in CLASSES and row['training_serving_parity'] in PARITY and
            row['prediction_time_availability'] in AVAILABILITY and row['safe_set'] in SETS,'Unknown candidate classification')
    require(row['reason'] and row['evidence_ids'],'Candidate provenance/reason absent')
    require(type(row['allowed_for_training']) is bool and type(row['allowed_for_deployment']) is bool,'Boolean permissions required')
    if row['allowed_for_training'] or row['allowed_for_deployment']:
        require(row['feature_class'] not in {'RETROSPECTIVE_ONLY','DESCRIPTIVE_ONLY','TARGET_OR_LABEL','UNRESOLVED','EXCLUDED'}
                and row['leakage_status']!='leakage_prohibited'
                and row['prediction_time_availability'] not in {'unresolved','prediction_time_unavailable','retrospectively_available'},'Unsafe input permission')
    if row['allowed_for_deployment']:
        require(bool(row['operational_source']) and row['training_serving_parity'] in {'EXACT','COMPATIBLE_WITH_CAVEATS'}
                and row['safe_set']=='SAFE_NOW','Deployable input requires operational source and validated parity')
    if row['feature_id'] in FORBIDDEN:
        require(not row['allowed_for_training'] and not row['allowed_for_deployment'] and row['safe_set']=='PROHIBITED','Forbidden predictor')
    if row['source_type']=='modelled_glofas_historical':
        require(row['feature_class']=='RETROSPECTIVE_ONLY' and row['prediction_time_availability']=='retrospectively_available',
                'Historical consolidated GloFAS cannot become operational forecast')
    if row['source']=='soi_2025':require(not row['allowed_for_deployment'],'Restricted SOI cannot deploy')
    return deepcopy(row)


def asof_input(row,value,issuance):
    """Future workflow gate only; never constructs features. Timestamps must be documented."""
    validate_candidate(row)
    require(row['feature_class'] in {'STATIC','OBSERVED_PAST','MODELLED_PAST','FORECAST'}
            and row['feature_id'] not in FORBIDDEN and row['safe_set'] in {'SAFE_NOW','SAFE_AFTER_VALIDATION'}
            and row['prediction_time_availability'] not in {'unresolved','prediction_time_unavailable','retrospectively_available'},'Not a prediction-time input')
    require(value.get('documented_availability') is True and value.get('availability_evidence_url','').startswith('https://')
            and re.fullmatch(r'[a-f0-9]{64}',value.get('availability_evidence_sha256','')),'Availability must be evidence-backed')
    def time(name):
        d=datetime.fromisoformat(value[name]);require(d.tzinfo is not None,'Timezone required');return d
    require(issuance.tzinfo is not None,'Issuance timezone required')
    require(time('available_at')<=issuance,'Value published/retrieved after issuance')
    if row['feature_class']=='FORECAST':
        require(time('initialized_at')<=time('available_at')<=issuance,'Forecast issue/availability leakage')
        require(time('interval_start')<time('interval_end'),'Forecast interval required')
    elif row['feature_class']=='STATIC':require(time('vintage_available_at')<=issuance,'Post-event static vintage leakage')
    else:require(time('interval_start')<time('interval_end')<=issuance,'Future observation/modelled elapsed interval')
    return True


def flood_target(status):
    require(status in {'satellite_positive','observed_zero_event','unlabeled_background','insufficient_observation','unknown'},'Unknown outcome class')
    # Evidence can support event/spatial positivity; does not yield a daily supervised target.
    return {'evidence_class':status,'event_window_positive':status=='satellite_positive','daily_label':None,'binary_training_target':None}


def matrix():
    C=candidate; rows=[]
    rows.append(C('chirps_final_daily','Native regional daily rainfall','chirps_catalogue','satellite_station_blend','mm/day','0.05deg EPSG4326','daily','31SOI2025polygons in2025; reviewed event scopes1981onwards catalogue','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','Final daily value is not available the same day; preliminary/version3 or NWP differs, requires separate validation',operational='CHIRPS Final delayed monitoring only; live rainfall proxy not selected',latency='Third week of following month; preliminary2days after pentad, not Final',licence='CHIRPS public domain; SOI-dependent detailed2025tables withheld',evidence=['chirps_faq','chirps_producer','chirps_catalogue']))
    rows.append(C('antecedent_rainfall','Stage3C/3D1/3/7/14/30day sums and7/14day maxima','chirps_catalogue','retrospective_antecedent_summary','mm','native regional cell-centre means','completed daily windows before GFDstart','4positive/2observed-zero scopes','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','Calendar cut-off satisfied but Final release was after anchor; not operational backtest',operational='No validated live equivalent; forecast/recent model estimates require validation',latency='Inherits delayed CHIRPS Final publication',licence='CHIRPS public domain;geoBoundariesCC BY;event-linkedGFDCC BY-NC;detailedtables local',evidence=['chirps_faq','chirps_catalogue','stage3c','stage3d']))
    rows.append(C('event_rainfall','Event-window rainfall totals/mean/max','stage3c','post_anchor_summary','mm','CHIRPS0.05deg regional means','GFDstart through end inclusive','4positive scopes','DESCRIPTIVE_ONLY','prediction_time_unavailable','NO_OPERATIONAL_EQUIVALENT','PROHIBITED','DESCRIPTIVE_ONLY_NOT_PREDICTION_FEATURE; includes event-start/future rain',evidence=['stage3c','stage3d']))
    rows.append(C('om_reanalysis_precip','Historical ERA5 precipitation through Open-Meteo','om_history','reanalysis','mm','ERA50.25deg;ERA5-Land0.1deg atmospheric precipitation caveat','hourly/daily','Global catalogue; no retained extraction in checkout','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','ERA5 is retrospectively reconstructed; not equivalent to live NWP estimates',operational='Open-Meteo forecast;requires distinct model/run validation',latency='Provider lists5day delay;record-specific final/revision time unverified',licence='CC BY4.0 data; hosted service terms apply',evidence=['om_history','om_terms']))
    rows.append(C('om_ifs_history','Open-Meteo historical IFS analysis','om_history','modelled_analysis','mm','9km','hourly','Global from2017catalogue;not acquired','MODELLED_PAST','unresolved','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Model changes and archive construction require as-of proof; no availability inferred from current archive',operational='Pinned Open-Meteo IFS live model',latency='Provider says6hourly/no delay;actual issue/delivery logs absent',licence='CC BY4.0;freehost noncommercial',evidence=['om_history','om_terms']))
    rows.append(C('om_current_precip','Current preceding-interval precipitation','om_forecast','weather_model_estimate','mm/returned interval','model-dependent global grid;coordinate is not rain gauge','returned current interval','Working app Bengaluru point only','MODELLED_PAST','near_real_time_available','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Operationally retrieved, but current value is model output; app omits issue/model-run IDs and no historical snapshots; no measured-past claim',operational='https://api.open-meteo.com/v1/forecast current.precipitation',latency='Underlying model cadence,not3minute cacheTTL;actual returned interval preserved',licence='CC BY4.0;freehost noncommercial',evidence=['om_forecast','om_terms','weather_adapter']))
    rows.append(C('om_forecast_precip','Issued weather-model precipitation forecast','om_forecast','weather_forecast','mm/hour or local-calendar-day total','model-dependent global grid','hourly;daily sums','Catalogueglobal;app3dailyBengaluru forecasts','FORECAST','forecast_available','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Forecast available by retrieval but issue time/model selection unknown;current day total mixes elapsed/future model periods,not observed antecedent rainfall',operational='https://api.open-meteo.com/v1/forecast hourly.precipitation/daily.precipitation_sum',latency='Model dependent;global commonly6h;need delivery/issuance snapshot',licence='CC BY4.0;noncommercial freehost;no SLA',evidence=['om_forecast','om_terms','weather_adapter']))
    rows.append(C('om_current_temperature_humidity','Existing current temperature and humidity context','om_forecast','weather_model_estimate','degC;percent','model dependent','returned current valid time','Working Bengaluru dashboard','MODELLED_PAST','near_real_time_available','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Actual adapter variables; no demonstrated flood-predictive usefulness, no observed-gauge claim',operational='Existing forecast API current temperature/humidity fields',licence='CC BY4.0;freehost noncommercial',evidence=['om_forecast','weather_adapter','om_terms']))
    rows.append(C('om_forecast_temperature','Daily temperature min/max forecast','om_forecast','weather_forecast','degC','model dependent global grid','daily calendar min/max','Working Bengaluru dashboard','FORECAST','forecast_available','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Forecast daily extremes must not be mistaken for elapsed observations; scientific relevance not established',operational='Existing forecast API daily.temperature_2m_min/max',licence='CC BY4.0;free hosted service non-commercial',evidence=['om_forecast','weather_adapter','om_terms']))
    rows.append(C('om_seamless_archive','Stitched historical forecast precipitation','om_historical_forecast','archived_model_forecasts','mm','model specific','continuous hourly','Broadly2021onward;catalogue only','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','Stitched early-run values are not full forecasts known at one historical issuance; JSON shape is not as-of parity',operational='Live seamless forecast API;run-pinning review required',licence='CC BY4.0/service terms',evidence=['om_historical_forecast']))
    for fid,src,label in [('om_previous_runs','om_previous','Fixed-lead past model runs'),('om_single_runs','om_single','Initialization-pinned full forecast runs')]:
        rows.append(C(fid,label,src,'archived_forecasts','mm','model specific','hourly validtime plus lead/run','Most previous runs2024;singleIFS2024-03-14/others2026-04-02;no proved2005–2010positive coverage','FORECAST','unresolved','COMPATIBLE_WITH_CAVEATS','SAFE_AFTER_VALIDATION','Potential as-of reconstruction only after pinned version/model/run, first-availability timing and location/horizon coverage validation;not acquired',operational='Same pinned live forecast model/run snapshots',latency='Initialization is not publication; archive existence is not historic availability',licence='CC BY4.0/service terms',evidence=[src,'om_terms']))
    for fid,label in [('sadalga_glofas_history','Sadalga supported model cell'),('huvinhedgi_glofas_history','Huvinhedgi supported model cell')]:
        rows.append(C(fid,label,'glofas_history','modelled_glofas_historical','m3/s','v5native0.05deg EPSG4326','preceding24h mean ending00UTC','Existing62intervalsJuly–August2019','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','2026v5consolidated2019simulation did not exist at2019issuance;historical context only;coordinate/calibration caveats',operational='GloFAS operational ensemble forecast/initialization, version parity unresolved',latency='Consolidated monthly;exact sample publication/revision unknown',licence='CEMS-FLOODS licence;source-specific/model-data policy review',evidence=['glofas_history','glofas_forecast','stage4f']))
    rows.append(C('gokak_discharge','Canonical Gokak model discharge','stage4f','modelled_glofas','m3/s','Two distinct0.05deg candidates','daily','2019candidate series retained','EXCLUDED','prediction_time_unavailable','UNRESOLVED','PROHIBITED','Gauge/reach remains ambiguous; do not select/average candidates or resolve from magnitude',evidence=['stage4f']))
    rows.append(C('glofas_intermediate','ERA5T intermediate modelled discharge','glofas_history','modelled_past','m3/s','0.05deg version-dependent','24h','Global catalogue;not acquired','MODELLED_PAST','unresolved','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Updated daily is not zero-latency; exact elapsed interval/publication/version/init states need validation',operational='cems-glofas-historical intermediate (not a forecast)',latency='Daily update; exact product delivery/forcing lag unverified',licence='CEMS-FLOODS terms',evidence=['glofas_history']))
    rows.append(C('glofas_ensemble_forecast','Forecast river discharge, separate from measured values','glofas_forecast','modelled_glofas_forecast','m3/s','listedv4native0.05deg EPSG4326','daily means;00UTC forecast cycles','Global inclKarnataka;service catalogue only','FORECAST','forecast_available','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','Must pin actual operational version,member,run,step and delivery. v5history cannot silently substitute;station relevance limited to supported reaches',operational='cems-glofas-forecast;documented operational route/service feasibility requires review',latency='Daily00UTC cycle not delivery guarantee;time-criticalEWDS warning',licence='CEMS-FLOODS terms;access acceptance handled separately',evidence=['glofas_forecast','glofas_forcing','glofas_v5_status']))
    rows.append(C('glofas_reforecast','Retrospective forecast-like hindcasts','glofas_reforecast','modelled_reforecasts','m3/s','listedv4native0.05deg','24h;twiceweekly initialization','2003–2022hindcast years catalogue;not acquired','RETROSPECTIVE_ONLY','retrospectively_available','PROXY_REQUIRES_VALIDATION','RESEARCH_ONLY','Produced later,not actual historic issued forecasts;future forcing/initial-state and model-vintage leakage must be audited;cannot establishas-of availability',operational='Version-matched GloFAS forecast after separate validation',licence='CEMS-FLOODS terms',evidence=['glofas_reforecast','glofas_forecast']))
    rows.append(C('cwc_daily_discharge','14quality-caveated measured discharge rows','stage4f','measured_cwc_nwdp','m3/sec','CWC stations;coordinates caveated','Nominaldaily;exact statistic/timezone/bounds unresolved','Sadalga2/Huvinhedgi12;Gokak0flood-period','UNRESOLVED','unresolved','UNRESOLVED','RESEARCH_ONLY','Observed/reported source class separate from model;historicalpublication latency and exact temporal equivalence unresolved',licence='NWDP Other(Open) not standardlicence;producerreuse unresolved',evidence=['stage4f']))
    rows.append(C('cwc_hourly_level','Measured hourly river level context','stage4f','measured_cwc_nwdp','m;datum unresolved','CWC stations','nominalhourly','Stage4B retained2019window','UNRESOLVED','unresolved','UNRESOLVED','RESEARCH_ONLY','Datum/reference stability,publicationtime/quality/coordinatehistory need review;no threshold or change features yet',licence='NWDP/CWCreuse unresolved',evidence=['stage4f']))
    for fid,name in [('water_level_threshold','Water-level threshold exceedance'),('cwc_model_skill','Quantitative CWC/GloFAS skill comparison')]:
        rows.append(C(fid,name,'stage4f','unsupported_derivation','not constructed','station','not constructed','No usable derivation','EXCLUDED','prediction_time_unavailable','UNRESOLVED','PROHIBITED','Stage4F datum/time/source eligibility prohibitions remain unchanged',evidence=['stage4f']))
    rows.append(C('future_discharge_peak','Full July–August2019 modelled maximum/date/rank','stage4d','full_window_descriptive','m3/s;date;rank','retained model cells','Full62interval window','Stage4Ddescriptivehydrograph','DESCRIPTIVE_ONLY','prediction_time_unavailable','NO_OPERATIONAL_EQUIVALENT','PROHIBITED','Full-window outcome/statistic requires future modelled elapsed values at earlier issuance;not a forecast peak',evidence=['stage4d']))
    for fid,name,units in [('surface_elevation','Surface elevation','m aboveEGM2008'),('surface_slope','Horn-derived surface slope','degrees')]:
        rows.append(C(fid,name,'dem_catalogue','dated_static_surface','%s'%units,'30m EPSG32643;sourceEPSG4326','2024_1release;2010–2020acquisitions','Existing3kmx3kmUdupi studywindow only','STATIC','historically_available','EXACT','SAFE_NOW','Available now as dated exploratoryresearchcontext;not bare-earthflow/drainageinfrastructure or statewidecoverage. Post-eventvintage excludesstrict2005–2010backtests',operational='Existing checksum-validated local drainage layer dataset',latency='Staticcached layer retrieved2026-10-03;originalearlierrelease day not inferred',licence='Copernicus WorldDEM30free licence with required attribution/adaptation/liability notices',deployment=True,evidence=['dem_catalogue','udupi_gis']))
    rows.append(C('landcover_2021','Dated2021 land-cover class','worldcover_catalogue','dated_static_landcover','classcode','10m EPSG32643 local/sourceEPSG4326','2021v200;2022citation','Existing3kmUdupionly','STATIC','historically_available','EXACT','SAFE_NOW','Known now as2021baseline;notcurrentlandcover or2005–2010conditions;nodata/localclassificationlimits retained',operational='Existing local land_cover raster with2021label',licence='CC BY4.0 ESAWorldCover attribution',deployment=True,evidence=['worldcover_catalogue','udupi_gis']))
    rows.append(C('v5_upstream_network','Model upstream area/channel/LDD context','stage4d','model_static_network','m2;channelflag;PCRasterdirection','0.05deg EPSG4326','v2.1.1OSLISFLOODv5release','Retainedglobalstatic;bounded30/48cellresearch','STATIC','unresolved','PROXY_REQUIRES_VALIDATION','SAFE_AFTER_VALIDATION','2026modelsetup unavailableas-such2019;futureversion-matchedmodelcontext at supportedcells only;not verifiedphysicaldrainage. Gokak topology cannot selectgauge',operational='Same version-compatible GloFAS static release, pendingforecast-version match',licence='JRCstatic CC BY4.0 plus model-policy review',evidence=['stage4d','stage4f','glofas_forecast']))
    rows.append(C('soi_district_geometry','SOI2025edition district association','soi_2025','administrative_geometry','sourcecodes/polygons','1:50000source;CRSvalidatedlocally','2025edition,not historicalvintage','31Karnatakapolygonslocal','STATIC','unresolved','NO_OPERATIONAL_EQUIVALENT','RESEARCH_ONLY','CurrentLGDindependentreconciliation andABDBreuse unresolved;derivedrainfalltableslocal;no upload/deployment ofrestrictedgeometry',licence='SOIpublication/internalreuse unresolved;conservative localpolicy',evidence=['soi_policy']))
    rows.append(C('public_review_boundary','geoBoundariesreview scope identity','stage3c','administrative_geometry','scopeidentifier','v6compositeEPSG4326;not a localitymeasurement','2023composite','ReviewedUdupi/Chitradurga/Kolarscopes','STATIC','unresolved','COMPATIBLE_WITH_CAVEATS','SAFE_AFTER_VALIDATION','Permittedpublicboundaryalternativecontext exists but not currentLGD or historicalboundary;no statewide foundation substitution',operational='Existing public reviewed geoBoundaries geometries',licence='CC BY4.0 with attribution',evidence=['stage3c']))
    rows.append(C('osm_drain_context','Mapped drain/ditch network coverage','osm_terms','mapped_static_infrastructure','geometry;not capacity','OSMline coordinates;CRS84/metricclip','Source2026querysnapshot','3kmUdupi;zero mappedwaysreturned','UNRESOLVED','unresolved','UNRESOLVED','RESEARCH_ONLY','No actual featuregeometry in boundedstudy;missingcoverage isunknown,not zero drainage or capacity',operational='OSMversionedquery/extract aftercoveragevalidation',licence='ODbL1.0 attribution/database obligations',evidence=['osm_terms','udupi_gis']))
    rows.append(C('invented_drain_capacity','Drainage capacity/score','udupi_gis','unsupported','unavailable','unavailable','unavailable','No measurements','EXCLUDED','prediction_time_unavailable','NO_OPERATIONAL_EQUIVALENT','PROHIBITED','Noverifiedpipe/capacity/blockage/discharge data;cannot manufacture or useQandAproxyassumptions'))
    rows.append(C('jrc_history','JRCfullhistorical water context','jrc_catalogue','retrospective_surface_water','occurrencepercent/classes','30m','1984–2021fullhistory','ExistingStage3auxdiagnostics','RETROSPECTIVE_ONLY','retrospectively_available','NO_OPERATIONAL_EQUIVALENT','RESEARCH_ONLY','Whole-history water occurrence andevent-year/month classes containpost-issuanceobservations;no static exemption. Needasofcutoff/version/releaseproofbeforefutureinput',licence='JRCcatalogue terms/attribution',evidence=['jrc_catalogue','stage3_aux']))
    for fid,name,source,kind in [('gfd_extent','GFD event-window floodwater evidence','gfd_catalogue','satellite_outcome'),('reported_ifi_event','IFIreported event identity/dates/description','stage3a','reported_outcome'),('post_event_sar','Sentinel1change/NRSCpost-event corroboration','stage3_aux','post_event_diagnostic')]:
        rows.append(C(fid,name,source,kind,'outcomeevidence','source-specific;GFD250m','eventwindow;notdailyoccurrence','Existingreviewedproducts','TARGET_OR_LABEL','prediction_time_unavailable','NO_OPERATIONAL_EQUIVALENT','PROHIBITED','Outcome/diagnostic evidence mustremainseparatefrompredictors;no dailylabelpromotion. ExistingSARdiagnosticsnotverifiedpositives',licence='GFD/IFICC BY-NC4.0;SAR/NRSCterms source-specific',evidence=[source]))
    for fid,name in [('observed_zero','Two usable reviewedmaps withzeroqualifyingcells'),('missing_as_negative','Missing/unknown flood observation')]:
        rows.append(C(fid,name,'stage3d','nonnegative_unlabeled_evidence','evidenceclass','reviewedscopes','specificmapwindow','2698Bijapur/3107Raichur;unknownotherwindows','TARGET_OR_LABEL','prediction_time_unavailable','NO_OPERATIONAL_EQUIVALENT','PROHIBITED','Neitherzero-mapfindingnornorecordcertifiesnonflood;nullbinarytargets preserved',evidence=['stage3d']))
    require(len({r['feature_id'] for r in rows})==len(rows),'Duplicate candidate IDs')
    return rows


def target_definition():
    spec=(ROOT/'QandA.md').read_text()
    require(all(t in spec for t in ['FR1','FR2','FR3','FR5','Low/Medium/High','every 6 hours']),'Original intent requires re-review')
    return {'status':'intended_product_known_operational_target_not_defined',
      'intended_question':'What is district/locality flood risk over each of the next seven forecast days?',
      'geographic_unit':'Mixed31districtsandlocalityrefinementaspiration;no verified locality training unit',
      'requested_outputs':['Low','Medium','High'],'requested_update_frequency':'6hours fromFR5;not currentlyimplemented',
      'requested_forecast_span':'7dailyweatherforecastdays fromFR3;not a defined7dayfloodprobability',
      'definition_gaps':['Riskclasses lackverified occurrence/impact/severitytargetandthresholds','Dailyonset/timewindow notobserved byGFDmaximumextent','No approveddistrict/locality correspondence orarea/timeaggregationrule'],
      'inconsistencies':['OriginalQandA obsoleteDoneclaims/proxylabels/seasonalsyntheticallocation conflict withcurrentread-onlyresearchREADME','Original3minuteTTLfreshnessdoesnotrepresentupstream6h/daily/monthlyproductlatency','Localitycentroid/disaggregation/drainagescore assumptions lackverifiedmeasurements','CurrentadapterfixedBengaluru3dayforecast,not31district169locality7dayriskservice'],
      'source_sections':['QandA§6FR1–FR5','QandA§7NFR7','QandA§8/9assumptions/constraints','README sources/limitations'],
      'selected_primary_horizon':None,'horizon_status':'prediction_horizon_not_yet_trainable',
      'supported_present_target':'Exploratoryevent-windowspatialpositiveevidenceonly;no daily flood/riskprobability target',
      'no_silent_target_choice':True}


def label_review():
    evidence=read(ROOT/'data/working/karnataka_event_comparison_v1/evidence.json')
    require(len(evidence)==6 and all(x['ml_binary_label'] is None for x in evidence),'Existing nulltarget policy changed')
    positive={str(x['gfd_id']):x['qualifying_floodwater_cells'] for x in evidence if x['evidence_class']=='satellite_positive'}
    require(positive=={'2728':33,'3551':23,'3652':2,'2758':329},'Positive regression changed')
    zero=sorted(x['gfd_id'] for x in evidence if x['evidence_class']=='observed_zero_event')
    require(zero==[2698,3107],'Observedzeroevidence changed')
    return {'satellite_positive_event_scopes':positive,'positive_independent_regions':3,'udupi_repeated_events':2,
      'observed_zero_maps':zero,'verified_nonflood_targets':0,'daily_flood_targets':0,'supervised_risk_class_targets':0,
      'positive_semantics':'Fourqualifyingwater event/scopemaxima at250m;2cell3652retainsweakerspatialextent/qualitycontext;not fourindependentclimates or statewide dailylabels',
      'ifi':'Reportedpositiveinventory/uncertainassociation,notabsenceinventory;no inventedmatchedlabels',
      'sar_nrsc':'Existingambiguous/insufficient/referenceunavailablediagnosticsnotadditionalpositives;NRSCdateddescriptiveevidencealone lacksmachine-readableindependentreference',
      'unknown_policy':'Unknown/unobserved/unreviewed/missingandzero-mapfindingsnevernonfloodtargets',
      'spatial_labels':'Existingqualifiedcelloutcomegeometrymayinformevent-spatialresearchwithmasks;samplingoutsidecannotdefinezeros',
      'sample_bias':'Selectivereview,coastalrepeatgeography,MODISmask/resolution/eventwindows,spatialdependence;no independentdailycasecontrolsample',
      'supervised_training_allowed':False,'evidence_counts_expanded':False}


def readiness():
    return {'FEATURE_READINESS':'LIMITED','LABEL_READINESS':'NOT_READY','TEMPORAL_ALIGNMENT_READINESS':'NOT_READY',
      'TRAINING_SERVING_PARITY':'NOT_READY','LICENCE_DEPLOYMENT_READINESS':'UNRESOLVED','SAMPLE_SIZE_READINESS':'NOT_READY',
      'status':'ml_training_not_ready','methodology_review_complete':True,'model_training_allowed':False,
      'frozen_training_dataset_allowed':False,'next_stage':'Stage5A bounded operational-source/as-of archive validation and explicit target protocol, plus independently dated flood-positive/comparison evidence development. No model fitting or fabricated negatives.'}


def input_records():
    paths=list(RAW.iterdir())+[ROOT/'QandA.md',ROOT/'README.md',ROOT/'backend/app/weather.py',
        ROOT/'docs/COMPARISON_EVIDENCE_METHOD.md',ROOT/'docs/GLOFAS_PILOT_METHOD.md',ROOT/'docs/EXTERNAL_HYDROLOGY_CLOSURE_METHOD.md',
        ROOT/'data/working/karnataka_event_comparison_v1/evidence.json',ROOT/'data/reference/karnataka_identity_policy_20261005_v1/publication_policy.json']
    for d in ['data/working/karnataka_positive_event_rainfall_v1','data/working/karnataka_event_comparison_v1',
              'data/working/karnataka_external_hydrology_closure_v1','data/working/karnataka_glofas_2019_pilot_v1',
              'data/processed/udupi_drainage_gis_v1','data/working/karnataka_chirps_soi2025_2025_v1',
              'data/working/karnataka_sentinel1_flood_pilot_v2','data/working/belagavi_2021_incidence_audit_v1']:
        paths.append(ROOT/d/'manifest.json')
    return [record(p) for p in sorted(set(paths))]


def prior_gate():
    p=ROOT/'scripts/close_external_hydrology.py';spec=importlib.util.spec_from_file_location('stage4f',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);s=m.validate()
    require(s['gokak_status']=='gokak_reach_externally_unresolved' and s['nwdp_status']=='nwdp_temporal_semantics_externally_unresolved'
            and s['quantitative_comparisons']==0,'Stage4Frestrictions changed')
    return s


def assemble():
    baseline=prior_gate(); docs=sources();rows=matrix();target=target_definition();labels=label_review()
    sets={name:[r['feature_id'] for r in rows if r['safe_set']==name] for name in sorted(SETS)}
    parity=[{k:r[k] for k in ['feature_id','source','source_type','units','spatial_resolution','temporal_resolution',
             'historical_availability','prediction_time_availability','operational_source','latency','training_serving_parity','reason']}
            | {'transformation':'Explicitlocalnativeaggregation/units/intervals/runmember/version matching; no calculation inStage5',
               'confidence':'Product semantics documented; empirical/as-of paritynotvalidated'} for r in rows]
    leakage=[{k:r[k] for k in ['feature_id','feature_class','prediction_time_availability','leakage_status','reason']}
             | {'at_issuance_T':'Require documentedavailable_at<=T;pastintervalend<=T;forecastruninit<=delivery<=T;staticversionexistsbeforeT',
                'historical_presence_not_availability':True} for r in rows]
    review={'dimensions':readiness(), 'safe_sets':sets,
        'safe_now_scope':'ThreeexistingdatedUdupi staticresearchlayersonly,currentcontext. No safe supervised floodfeature setexists yet;all allowed_for_training false.',
        'asof_schema':['issued_at','initialized_at','available_at','retrieved_at','valid_interval_start','valid_interval_end',
                        'product_version','model_version','ensemble_member','geometry_version','units','mask_quality','first_available_evidence'],
        'clock_rules':'UTCinstantspluslocalcalendarintervalswithoffset;retrieval!=initialization/publication/observation. Keeprequested versusactualsourcecoordinates/resolution. Current-day totals are not priorcomplete24h rainfall.',
        'no_operational_substitution':'Reanalysis/Final/hindcasts mayserve researchonly unless separateas-of/causalinitialization/productdistribution validation;neverreplace measured gaps.',
        'future_join_rule':'Joinbyreviewedscope/compatibleintervalandproductversion,notjustdate/stringstationname. Stationcatchments/districts/localitiesdiffer; includeupstreambeyondKarnataka infutureprotocol.'}
    conflicts=[{'sources':['glofas_history','glofas_v5_status','glofas_forecast'],
                'finding':'Currenthistoricalcataloguecallsv5operational;July2026notecallsv5preoperational/v4operational;forecastcataloguelistsv4. No sourcepreference orversionmixing.',
                'decision':'operational_v5_forecast_parity_unresolved'},
               {'sources':['glofas_forcing','glofas_forecast'],
                'finding':'Currentmedium15day/subseasonal46dayproductsversusEWDSlegacy30dayarchiveare distinct;first15daysrelatedbutdelivery/versionmustbeverified',
                'decision':'Do notassignallhorizons tooneproduct'},
               {'sources':['om_history','om_historical_forecast','om_single'],
                'finding':'ERA5/IFSanalysis,stitchedforecasts,fixedleadarchivesandpinnedrunsdiffer evenwhenformatsmatch',
                'decision':'No EXACTrainfalltraining-servingparity established'}]
    horizon={'status':'prediction_horizon_not_yet_trainable','recommended_primary_horizon':None,
        'intent':'Sevenforecastdays withsixhourupdates;daily leadwindow withinspan isplausible but floodtarget/issuancecalendar boundaries undefined',
        'assessments':[{'candidate':'onecalendarforecastday withinrequestedseven-day span','weather':'Provider leadexists;currentapp3days/modelnotpinned',
                       'hydrology':'Globalmodeldailyforecastleadexists;version/cell/timecriticaldeliverygates',
                       'labels':'GFDmaxextentcannotidentifydailyoccurrence/onset','asof_training':'2005–2010positivecontexts lackconfirmedissued-runarchives','trainable':False},
                       {'candidate':'sevenforecastdays aspiration','weather':'API7daycapabilityexists;doesnotdefineone7dayfloodoutcome',
                       'hydrology':'Leadcapacitydoesnotprovelocalriskvalidity','labels':'No explicit7daytarget/classesorbalancedtrainingevidence',
                       'asof_training':'No retainedprediction-issuedcounterpart at fourpositiveanchors','trainable':False}],
        'not_adopted':['current-risknowcast','6h','12h','48h','72h'],'not_adopted_reason':'Not separately defined byexistingrequirements;no silentnewhorizon target'}
    questions=[{'id':'target','question':'Define occurrence versusimpact/severity/susceptibility and Low/Medium/High evidence, geographicunit/aggregation and exactissue/validintervals before selecting primaryhorizon.'},
               {'id':'parity','question':'Validateonepinnedoperationalmodel andissuance-preservingrainfallarchivewithdocumentedfirstavailability;do not substituteCHIRPSFinal orstitchedanalysis.'},
               {'id':'hydrology','question':'ConfirmofficialoperationalGloFASmajorversion,deliveryroute/latency/licence,versioncompatiblestaticsandarchived/reforecastinitializationsemantics;keepGokakandCWCclosure exclusions.'},
               {'id':'labels','question':'Acquireindependentlytime-resolvedpositive/comparisonobservationevidence in compatibleforecastarchiveperiod;noabsence-derivednegatives;sampledependency/coverage/qualitydocumented.'},
               {'id':'reuse','question':'ResolveSOI-deriveddeployment andCWC/IFI/GFDcommercial/modelderivative rights beforepublishingdetailedtables orweights;data licenceandhostedservicepermissions differ.'}]
    summary={'stage':'5','status':'ml_training_not_ready','methodology_review_complete':True,'candidate_count':len(rows),
       'category_counts':{k:sum(r['feature_class']==k for r in rows) for k in sorted(CLASSES)},
       'safe_set_counts':{k:len(v) for k,v in sets.items()},'approved_training_features':0,
       'context_only_deployable_layers':sum(r['allowed_for_deployment'] for r in rows),
       'selected_primary_horizon':None,'horizon_status':horizon['status'],'supervised_labels':0,'verified_negative_targets':0,
       'existing_positive_scopes':labels['satellite_positive_event_scopes'],'models_trained':0,'features_calculated':0,
       'observations_extracted':0,'quantitative_hydrology_comparisons':0,'documentation_sources':len(docs),
       'protected_hydrology_counts':{k:baseline[k] for k in ['preserved_measured_rows','preserved_comparison_cases','preserved_eligible_rows','preserved_disagreements']}}
    artifacts={'prediction_target_definition.json':target,'feature_source_register.json':docs,'feature_availability_matrix.json':rows,
       'rainfall_availability_review.json':{'candidates':[r for r in rows if r['feature_id'].startswith(('chirps','antecedent','event_rainfall','om_'))],
           'CHIRPS_latency':'Finalthirdweekfollowingmonth;Prelim2daysafterpentad;not same-dayFinal. Record-specifichistoricalreleaseunknown.',
           'retirement':'Producerendsv2productionafterDecember2026;noautomaticswitchv3','operational_reanalysis_extraction_in_repository':False},
       'hydrology_availability_review.json':{'candidates':[r for r in rows if 'glofas' in r['feature_id'] or r['feature_id'].startswith(('cwc','gokak','water_level','future_discharge'))],
           'conflicts':conflicts[:2],'stage4f_restrictions':baseline,'glofas_historical_not_forecast':True},
       'static_feature_review.json':{'candidates':[r for r in rows if r['feature_class']=='STATIC' or r['feature_id'] in {'osm_drain_context','jrc_history','invented_drain_capacity'}],
           'unavailable_not_candidates':['Verifiedmetricriverdistance','Reservoirproximity/capacity','Undergrounddrainnetwork','CurrentLGDcanonical31registry','Verifiedlocalityprofiles'],
           'no_static_vintage_exemption':True,'Udupi_window_not_official_municipality':True},
       'label_readiness_review.json':labels,'leakage_register.json':leakage,'training_serving_parity_matrix.json':parity,
       'forecast_horizon_assessment.json':horizon,'safe_feature_sets.json':review,'ml_readiness_decision.json':readiness(),
       'unresolved_questions.json':questions,'source_disagreements.json':conflicts,'stage5_summary.json':summary}
    return {n:encode(v) for n,v in artifacts.items()},summary


def build(output=OUTPUT):
    p=Path(output);require(not p.exists(),'ImmutableStage5versionexists')
    artifacts,summary=assemble();manifest={'version':'karnataka_prediction_methodology_v1','created_at':datetime.now(timezone.utc).isoformat(),
        'inputs':input_records(),'processing_code':record(Path(__file__)),'summary':summary,
        'files':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in artifacts.items()}}
    p.mkdir(parents=True)
    for n,b in artifacts.items():(p/n).write_bytes(b)
    (p/'manifest.json').write_bytes(encode(manifest));return summary


def validate(output=OUTPUT):
    p=Path(output);m=read(p/'manifest.json');require(m['inputs']==input_records() and m['processing_code']==record(Path(__file__)),'Input/code checksumchanged')
    artifacts,summary=assemble();require(m['summary']==summary and set(m['files'])==set(artifacts),'Manifestchanged')
    for n,b in artifacts.items():require((p/n).read_bytes()==b and m['files'][n]=={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()},'Reviewreproductionfailed')
    return summary


def public_metadata(output=OUTPUT):
    validate(output);p=Path(output)
    docs=[{k:v for k,v in r.items() if k!='finding'} for r in read(p/'feature_source_register.json')]
    # Own methodology only. No QandA contents, geometry, rainfall/hydrology values or sourceHTML/PDFs.
    return {**read(p/'manifest.json'),'local_manifest_sha256':sha(p/'manifest.json'),'sources':docs,
        'target':read(p/'prediction_target_definition.json'),'candidates':read(p/'feature_availability_matrix.json'),
        'safe_sets':read(p/'safe_feature_sets.json'),'readiness':read(p/'ml_readiness_decision.json'),
        'horizons':read(p/'forecast_horizon_assessment.json'),'source_disagreements':read(p/'source_disagreements.json'),
        'publication':'Permittedownmethodology/sourceIDs/URLs/checksums/counts only;sourcebinaries/restrictedtables/geometrystaylocal'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['build','validate','publish-metadata']);parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    if args.command=='publish-metadata':
        meta=public_metadata(args.output);PUBLIC.parent.mkdir(parents=True,exist_ok=True)
        with PUBLIC.open('xb') as f:f.write(encode(meta))
        print(json.dumps({'public_manifest':str(PUBLIC)}))
    else:print(json.dumps((build if args.command=='build' else validate)(args.output),indent=2))
