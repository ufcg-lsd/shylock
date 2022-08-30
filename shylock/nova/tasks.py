import ast

from celery import shared_task
from django.conf import settings
from novaclient import client as nova_client

from nova.models import *

nova = nova_client.Client(
    version='2.1',
    session=settings.OPENSTACK_SESSION,
    endpoint_type='public',
)


@shared_task
def save_services() -> None:
    """Create or update existing services."""

    # retrieve all services
    services = nova.services.list()
    for service in services:
        service = service.to_dict()
        try:
            service_obj = Services.objects.get(id=service['id'])
        except Services.DoesNotExist:
            service_obj = Services()

        service_obj.id = service['id']
        service_obj.binary = service['binary']
        service_obj.disabled_reason = service['disabled_reason']
        service_obj.host = service['host']
        service_obj.state = service['state']
        service_obj.status = service['status']
        # if date is not empty, add Z at the end to inform UTC timezone
        updated_at = service.get('updated_at')
        if updated_at:
            updated_at = updated_at + 'Z'
        service_obj.updated_at = updated_at
        service_obj.zone = service['zone']
        service_obj.save()


@shared_task
def save_hypervisors() -> None:
    """Create or update existing hypervisors."""

    # retrieve all services
    hypervisors = nova.hypervisors.list()
    for hypervisor in hypervisors:
        hypervisor = hypervisor.to_dict()
        try:
            hypervisor_obj = Hypervisors.objects.get(id=hypervisor['id'])
        except Hypervisors.DoesNotExist:
            hypervisor_obj = Hypervisors()

        try:
            service_obj = Services.objects.get(id=hypervisor['service']['id'])
        except Services.DoesNotExist:
            service_obj = None

        hypervisor_obj.id = hypervisor['id']
        # convert string dict to dict object
        hypervisor['cpu_info'] = ast.literal_eval(hypervisor['cpu_info'])
        hypervisor_obj.vendor = hypervisor['cpu_info']['vendor']
        hypervisor_obj.model = hypervisor['cpu_info']['model']
        hypervisor_obj.arch = hypervisor['cpu_info']['arch']
        hypervisor_obj.cores = hypervisor['cpu_info']['topology']['cores']
        hypervisor_obj.cells = hypervisor['cpu_info']['topology']['cells']
        hypervisor_obj.threads = hypervisor['cpu_info']['topology']['threads']
        hypervisor_obj.sockets = hypervisor['cpu_info']['topology']['sockets']
        hypervisor_obj.host_ip = hypervisor['host_ip']
        hypervisor_obj.hypervisor_hostname = hypervisor['hypervisor_hostname']
        hypervisor_obj.hypervisor_type = hypervisor['hypervisor_type']
        hypervisor_obj.hypervisor_version = hypervisor['hypervisor_version']
        hypervisor_obj.local_gb = hypervisor['local_gb']
        hypervisor_obj.local_gb_used = hypervisor['local_gb_used']
        hypervisor_obj.memory_mb = hypervisor['memory_mb']
        hypervisor_obj.memory_mb_used = hypervisor['memory_mb_used']
        hypervisor_obj.running_vms = hypervisor['running_vms']
        hypervisor_obj.service = service_obj
        hypervisor_obj.state = hypervisor['state']
        hypervisor_obj.status = hypervisor['status']
        hypervisor_obj.vcpus = hypervisor['vcpus']
        hypervisor_obj.vcpus_used = hypervisor['vcpus_used']
        hypervisor_obj.save()


@shared_task
def save_aggregates() -> None:
    """Create or update existing aggregates."""

    # retrieve all aggregates
    aggregates = nova.aggregates.list()
    for aggregate in aggregates:
        aggregate = aggregate.to_dict()
        try:
            aggregate_obj = Aggregates.objects.get(id=aggregate['id'])
        except Aggregates.DoesNotExist:
            aggregate_obj = Aggregates()

        aggregate_obj.id = aggregate['id']
        aggregate_obj.name = aggregate['name']
        aggregate_obj.availability_zone = aggregate['availability_zone']
        created_at = aggregate.get('created_at')
        if created_at:
            created_at = created_at + 'Z'
        aggregate_obj.created_at = created_at
        deleted_at = aggregate.get('deleted_at')
        if deleted_at:
            deleted_at = deleted_at + 'Z'
        aggregate_obj.deleted_at = deleted_at
        updated_at = aggregate.get('updated_at')
        if updated_at:
            updated_at = updated_at + 'Z'
        aggregate_obj.updated_at = updated_at
        aggregate_obj.deleted = aggregate['deleted']
        # we must save before set to many fields
        aggregate_obj.save()

        service_hosts = Services.objects.filter(host__in=aggregate['hosts'])
        aggregate_obj.hosts.set(service_hosts, clear=True)


@shared_task
def save_flavors() -> None:
    """Create or update existing flavors."""

    # retrieve all flavors
    # non public flavors
    flavors = nova.flavors.list(is_public=False)
    # public flavors
    flavors = flavors + nova.flavors.list()
    for flavor in flavors:
        flavor_properties = flavor.get_keys()
        flavor = flavor.to_dict()

        try:
            flavor_obj = Flavors.objects.get(id=flavor['id'])
        except Flavors.DoesNotExist:
            flavor_obj = Flavors()

        flavor_obj.id = flavor['id']
        flavor_obj.name = flavor['name']
        flavor_obj.swap = flavor['swap']
        flavor_obj.rxtx_factor = flavor['rxtx_factor']
        flavor_obj.is_public = flavor['os-flavor-access:is_public']
        flavor_obj.vcpus = flavor['vcpus']
        flavor_obj.ram = flavor['ram']
        flavor_obj.disk = flavor['disk']

        # check if flavor has been associated to an aggregate
        aggregate_name = ''
        for key in flavor_properties:
            if 'aggregate_instance_extra_specs' in key:
                aggregate_name = flavor_properties[key]

        # filter using the icontains is non-case-sensitive.
        # the lower() guarantee the non-case-sensitive for
        # match the aggregate name
        aggregates = Aggregates.objects.filter(name__icontains=aggregate_name)
        aggregate_obj = None
        for aggregate in aggregates:
            if aggregate.name.lower() == aggregate_name.lower():
                aggregate_obj = aggregate

        flavor_obj.aggregate = aggregate_obj
        flavor_obj.save()


@shared_task
def save_servers() -> None:
    """Create or update existing servers."""

    # retrieve all servers from all tenants
    servers = nova.servers.list(search_opts={'all_tenants': 1})
    servers = servers + nova.servers.list(search_opts={'deleted': 1})
    for server in servers:
        server = server.to_dict()

        try:
            server_obj = Servers.objects.get(id=server['id'])
        except Servers.DoesNotExist:
            server_obj = Servers()

        server_obj.id = server['id']
        server_obj.name = server['name']
        server_obj.status = server['status']
        server_obj.user_id = server['user_id']
        # check if server has been created from an image
        if isinstance(server['image'], dict):
            image = server['image'].get('id')
        else:
            image = None
        server_obj.image_id = image
        server_obj.created = server['created']
        server_obj.updated = server['updated']

        # get project model
        try:
            project_obj = Projects.objects.get(id=server['tenant_id'])
        except Projects.DoesNotExist:
            project_obj = None
        server_obj.tenant_id = project_obj

        # get flavor model
        try:
            flavor_obj = Flavors.objects.get(id=server['flavor']['id'])
        except Flavors.DoesNotExist:
            flavor_obj = None
        server_obj.flavor = flavor_obj

        server_obj.save()

        # get server model updated
        server_obj = Servers.objects.get(id=server['id'])

        for key in server['addresses']:
            for address in server['addresses'][key]:
                # create addresses from server
                try:
                    address_obj = ServerAddresses.objects.get(
                        addr=address['addr'])
                except ServerAddresses.DoesNotExist:
                    address_obj = ServerAddresses()

                address_obj.type = address['OS-EXT-IPS:type']
                address_obj.addr = address['addr']
                address_obj.version = address['version']
                address_obj.server = server_obj
                address_obj.save()


@shared_task
def save_instance_actions() -> None:
    """Create or update instance actions like created or paused."""

    # retrieve all servers from all tenants
    servers = nova.servers.list(search_opts={'all_tenants': 1})
    servers = servers + nova.servers.list(search_opts={'deleted': 1})
    for server in servers:
        actions = nova.instance_action.list(server)

        for action in actions:
            action = action.to_dict()

            try:
                action_obj = InstanceActions.objects.get(
                    request_id=action['request_id'])
            except InstanceActions.DoesNotExist:
                action_obj = InstanceActions()

            # this could raise an exception
            try:
                project = Projects.objects.get(id=action['project_id'])
            except Projects.DoesNotExist:
                project = None
            action_obj.project = project
            action_obj.action = action['action']
            # this could raise an exception
            action_obj.instance = Servers.objects.get(id=server.id)
            action_obj.request_id = action['request_id']
            action_obj.start_time = action['start_time'] + 'Z'
            action_obj.user_id = action['user_id']

            action_obj.save()
