-- Exercise workspace provisioning, caller-JWT RLS, persistence, AWS quota, and budgets.
set request.jwt.claim.sub = '22222222-2222-4222-8222-222222222222';
set role authenticated;

select public.get_or_create_my_org() as created_workspace \gset
select 1 / case when public.get_my_org_role(:'created_workspace') = 'owner' then 1 else 0 end as assert_owner_role;

select public.persist_analysis_bundle(jsonb_build_object(
  'target_org', :'created_workspace',
  'analysis', jsonb_build_object('id','analysis-1','source','aws_cost_explorer','anomaly',jsonb_build_object('service','Amazon EC2'),
    'partial_data',true,'data_warnings',jsonb_build_array('PARTIAL_DATA: fixture warning')),
  'decision', jsonb_build_object('id','decision-1','trace',jsonb_build_object('decision','review')),
  'report', jsonb_build_object('id','report-1','report',jsonb_build_object('summary','test'),'storage_path', :'created_workspace' || '/report-1.json')
));
insert into public.aws_account_connections(organization_id,role_arn,external_id,account_id,updated_by)
values (:'created_workspace','arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','123456789012',auth.uid());
select 1 / case when public.reserve_aws_cost_query(:'created_workspace', 1) then 1 else 0 end as assert_first_request;
select 1 / case when not public.reserve_aws_cost_query(:'created_workspace', 1) then 1 else 0 end as assert_second_request_denied;
select 1 / case when not public.reserve_aws_cost_query(:'created_workspace', 1) then 1 else 0 end as assert_third_request_denied;

reset role;
select 1 / case when (select request_count from public.aws_cost_query_usage) = 2 then 1 else 0 end as assert_quota_counter_saturated;

set role authenticated;
insert into public.workspace_finops_settings(organization_id,monthly_budget,currency,updated_by)
values (:'created_workspace',1000,'USD',auth.uid());
update public.workspace_finops_settings set monthly_budget=1200
where organization_id=:'created_workspace';

reset role;
set request.jwt.claim.sub = '33333333-3333-4333-8333-333333333333';
set role authenticated;
select 1 / case when (select count(*) from public.cost_analyses) = 0 then 1 else 0 end as assert_unassociated_user_cannot_read;

reset role;
set role anon;
select 1 / case when public.cloudcost_sentinel_schema_version() = 'cloudcost-sentinel-v6' then 1 else 0 end
  as assert_production_readiness_probe;

reset role;
select 1 / case when (select partial_data and data_warnings = '["PARTIAL_DATA: fixture warning"]'::jsonb
  from public.cost_analyses where id = 'analysis-1') then 1 else 0 end as assert_analysis_quality_metadata;
