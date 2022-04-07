import re

from celery import shared_task
from cinderclient import client as cinder_client
from django.conf import settings
from keystoneclient.v3 import client as keystone_client
from neutronclient.v2_0 import client as neutron_client
from novaclient import client as nova_client

from keystone.models import *

keystone = keystone_client.Client(
    session=settings.OPENSTACK_SESSION,
    interface='public'
)


@shared_task
def save_domains() -> None:
    """Create or update existing domains."""

    # retrieve all domains
    domains = keystone.domains.list()
    for domain in domains:
        domain = domain.to_dict()
        # check if domain already exists
        # if True update, otherwise create a new
        try:
            domain_obj = Domains.objects.get(id=domain['id'])
        except Domains.DoesNotExist:
            domain_obj = Domains()

        domain_obj.id = domain['id']
        domain_obj.description = domain['description']
        domain_obj.enabled = domain['enabled']
        domain_obj.name = domain['name']
        domain_obj.save()


@shared_task
def save_projects_and_sponsors() -> None:
    """Create or update projects and sponsors."""

    # retrieve all sponsors and projects
    projects = keystone.projects.list()
    for project in projects:
        project = project.to_dict()

        sponsor = _save_sponsor(project['description'])
        # this could raise an exception
        domain = Domains.objects.get(id=project['domain_id'])

        try:
            project_obj = Projects.objects.get(id=project['id'])
        except Projects.DoesNotExist:
            project_obj = Projects()

        project_obj.id = project['id']
        project_obj.description = project['description']
        project_obj.domain_id = domain
        project_obj.sponsor = sponsor
        project_obj.enabled = project['enabled']
        project_obj.is_domain = project['is_domain']
        project_obj.name = project['name']
        project_obj.parent_id = project['parent_id']
        project_obj.save()


def _save_sponsor(project_description) -> None:
    # split with regex in multiple delimiters
    sponsor_raw = re.split('[,|:]', project_description)
    for sponsor in sponsor_raw:
        sponsor = sponsor.strip()
        # sponsor is a email on description field
        if '@' in sponsor:
            try:
                sponsor_obj = Sponsors.objects.get(email=sponsor)
            except Sponsors.DoesNotExist:
                sponsor_obj = Sponsors()

            sponsor_obj.email = sponsor
            sponsor_obj.save()

    try:
        sponsor = Sponsors.objects.get(email=sponsor)
    except BaseException:
        sponsor = None

    return sponsor


@shared_task
def save_services() -> None:
    """Create or update existing services."""

    services = keystone.services.list()
    for service in services:
        service = service.to_dict()

        try:
            service_obj = Services.objects.get(id=service['id'])
        except Services.DoesNotExist:
            service_obj = Services()

        service_obj.id = service['id']
        service_obj.description = service.get('description', '')
        service_obj.enabled = service['enabled']
        service_obj.name = service['name']
        service_obj.type = service['type']
        service_obj.save()


@shared_task
def save_regions() -> None:
    """Create or update existing regions."""

    regions = keystone.regions.list()
    for region in regions:
        region = region.to_dict()

        try:
            region_obj = Regions.objects.get(id=region['id'])
        except Regions.DoesNotExist:
            region_obj = Regions()

        region_obj.id = region['id']
        region_obj.description = region.get('description', '')
        region_obj.parent_region_id = region['parent_region_id']
        region_obj.save()


@shared_task
def save_quotas() -> None:
    """Create or update existing project quotas."""

    nova = nova_client.Client(
        version='2.1',
        session=settings.OPENSTACK_SESSION,
        endpoint_type='public',
    )

    cinder = cinder_client.Client(
        version='3.40',
        session=settings.OPENSTACK_SESSION
    )

    neutron = neutron_client.Client(
        session=settings.OPENSTACK_SESSION
    )

    for project in Projects.objects.all():
        nova_quotas = nova.quotas.get(tenant_id=project.id).to_dict()
        cinder_quotas = cinder.quotas.get(tenant_id=project.id).to_dict()
        neutron_quotas = neutron.show_quota_details(tenant_id=project.id)

        try:
            quotas_obj = ProjectQuotas.objects.get(project=project)
        except ProjectQuotas.DoesNotExist:
            quotas_obj = ProjectQuotas()

        quotas_obj.project = project
        quotas_obj.cores = nova_quotas['cores']
        quotas_obj.ram = nova_quotas['ram']
        quotas_obj.instances = nova_quotas['instances']
        quotas_obj.volumes = cinder_quotas['volumes']
        quotas_obj.gigabytes = cinder_quotas['gigabytes']
        quotas_obj.backups = cinder_quotas['backups']
        quotas_obj.backup_gigabytes = cinder_quotas['backup_gigabytes']
        quotas_obj.snapshots = cinder_quotas['snapshots']
        quotas_obj.floatingip_limit = neutron_quotas['quota']['floatingip']['limit']
        quotas_obj.floatingip_reserved = neutron_quotas['quota']['floatingip']['reserved']
        quotas_obj.floatingip_used = neutron_quotas['quota']['floatingip']['used']
        quotas_obj.loadbalancer_limit = neutron_quotas['quota']['loadbalancer']['limit']
        quotas_obj.loadbalancer_reserved = neutron_quotas['quota']['loadbalancer']['reserved']
        quotas_obj.loadbalancer_used = neutron_quotas['quota']['loadbalancer']['used']
        quotas_obj.save()
