data comes from:
https://sql.telemetry.mozilla.org/queries/new

using this sql on the treeherder data source:
select distinct jn.text as fixed_by_revision, p.revision as failed_revision, op.name as platform_option, j.id as job_id, tle.line as failure, bp.platform as platform from job_note jn, job j, push p, job_type jt, reference_data_signatures sig, option_collection oc, `option` op, build_platform bp, repository, text_log_step tls, text_log_error tle where jn.failure_classification_id=2 and jn.text!='' and jn.created>'2018-04-30' and jn.job_id=j.id and j.job_type_id=jt.id and j.signature_id=sig.id and sig.option_collection_hash=oc.option_collection_hash and oc.option_id=op.id and jt.name like 'test-%' and j.build_platform_id=bp.id and j.repository_id=repository.id and (repository.name='mozilla-inbound' or repository.name='autoland') and j.push_id=p.id and j.id=tls.job_id and tls.id=tle.step_id and tle.line not like '%leakcheck%' and tle.line like '%UNEXPECTED%';



save the data in a .csv format to SETA_testnames.csv
run: python localseta.py
* profit