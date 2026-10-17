-- PantheraLAB · private multi-institutional jaguar libraries (v1)
-- Run in Supabase SQL Editor on a *reviewed* project. Never ship service_role credentials.
create extension if not exists pgcrypto;

create table if not exists public.pl_organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 2 and 120),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);
create table if not exists public.pl_memberships (
  organization_id uuid not null references public.pl_organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'owner' check (role in ('owner','researcher','viewer')),
  created_at timestamptz not null default now(),
  primary key (organization_id,user_id)
);

create or replace function public.pl_is_member(p_organization uuid)
returns boolean language sql stable security definer
set search_path = '' as $$
  select exists(select 1 from public.pl_memberships m
                where m.organization_id = p_organization and m.user_id = (select auth.uid()));
$$;
revoke all on function public.pl_is_member(uuid) from public;
grant execute on function public.pl_is_member(uuid) to authenticated;

create or replace function public.pl_can_write(p_organization uuid)
returns boolean language sql stable security definer
set search_path = '' as $$
  select exists(select 1 from public.pl_memberships m
                where m.organization_id = p_organization and m.user_id = (select auth.uid())
                and m.role in ('owner','researcher'));
$$;
revoke all on function public.pl_can_write(uuid) from public;
grant execute on function public.pl_can_write(uuid) to authenticated;

create or replace function public.pl_add_creator()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.pl_memberships(organization_id,user_id,role)
  values(new.id,new.created_by,'owner');
  return new;
end;
$$;
drop trigger if exists pl_organization_created on public.pl_organizations;
create trigger pl_organization_created after insert on public.pl_organizations
for each row execute function public.pl_add_creator();

create table if not exists public.pl_studies (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.pl_organizations(id) on delete cascade,
  title text not null check (char_length(trim(title)) between 2 and 150),
  country text not null default '',
  created_at timestamptz not null default now(),
  unique (id,organization_id)
);
create table if not exists public.pl_individuals (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  study_id uuid not null,
  code text not null check (char_length(trim(code)) between 1 and 80),
  alias text not null default '',
  species text not null default 'Panthera onca',
  sex text not null default 'unknown' check(sex in ('unknown','male','female')),
  age_class text not null default 'unknown'
    check(age_class in ('unknown','juvenile','subadult','adult')),
  review_status text not null default 'provisional'
    check(review_status in ('provisional','verified')),
  notes text not null default '',
  created_at timestamptz not null default now(),
  unique(study_id,code),
  unique(id,study_id,organization_id),
  foreign key (study_id,organization_id)
    references public.pl_studies(id,organization_id) on delete cascade
);
create table if not exists public.pl_reference_photos (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  study_id uuid not null,
  individual_id uuid not null,
  storage_path text not null unique,
  filename text not null,
  flank text not null default 'unknown' check(flank in ('left','right','unknown')),
  photo_review_status text not null default 'unreviewed'
    check(photo_review_status in ('unreviewed','reviewed')),
  created_at timestamptz not null default now(),
  foreign key (individual_id,study_id,organization_id)
    references public.pl_individuals(id,study_id,organization_id) on delete cascade
);
create index if not exists pl_individuals_by_study on public.pl_individuals(study_id);
create index if not exists pl_photos_by_study on public.pl_reference_photos(study_id);
create index if not exists pl_studies_by_org on public.pl_studies(organization_id);

alter table public.pl_organizations enable row level security;
alter table public.pl_memberships enable row level security;
alter table public.pl_studies enable row level security;
alter table public.pl_individuals enable row level security;
alter table public.pl_reference_photos enable row level security;

-- Owners are inserted through a trigger. There is intentionally NO public
-- membership insert/update policy: team invites need a separate audited flow.
create policy "pl_org_read_members" on public.pl_organizations
for select to authenticated using (public.pl_is_member(id));
create policy "pl_org_create_self" on public.pl_organizations
for insert to authenticated with check (created_by = (select auth.uid()));
create policy "pl_membership_read_self" on public.pl_memberships
for select to authenticated using (user_id = (select auth.uid()));
create policy "pl_study_read" on public.pl_studies
for select to authenticated using (public.pl_is_member(organization_id));
create policy "pl_study_insert" on public.pl_studies
for insert to authenticated with check (public.pl_can_write(organization_id));
create policy "pl_individual_read" on public.pl_individuals
for select to authenticated using (public.pl_is_member(organization_id));
create policy "pl_individual_insert" on public.pl_individuals
for insert to authenticated with check (public.pl_can_write(organization_id));
create policy "pl_individual_update" on public.pl_individuals
for update to authenticated using (public.pl_can_write(organization_id))
with check (public.pl_can_write(organization_id));
create policy "pl_photo_read" on public.pl_reference_photos
for select to authenticated using (public.pl_is_member(organization_id));
create policy "pl_photo_insert" on public.pl_reference_photos
for insert to authenticated with check (public.pl_can_write(organization_id));

-- Bucket is never public; exact object path: organization/study/random-name.jpg
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('pantheralab-private','pantheralab-private',false,8388608,
  array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;

create policy "pl_photos_select" on storage.objects
for select to authenticated using(
  bucket_id='pantheralab-private' and
  exists(select 1 from public.pl_memberships m
    where m.organization_id::text=(storage.foldername(name))[1]
    and m.user_id=(select auth.uid()))
);
create policy "pl_photos_insert" on storage.objects
for insert to authenticated with check(
  bucket_id='pantheralab-private' and
  exists(select 1 from public.pl_memberships m
    where m.organization_id::text=(storage.foldername(name))[1]
    and m.role in ('owner','researcher')
    and m.user_id=(select auth.uid()))
);

-- NO public read, NO anonymous write, NO public bucket, NO service-role on client.
-- Do not create sharing/invite policies until an auditable permission workflow exists.
