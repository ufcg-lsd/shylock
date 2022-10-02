import datetime
import io
import math

from cinder.models import *
from django.core.files.storage import default_storage
from django.db.models import Count, Sum
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone
from keystone.models import *
from monasca.tasks import influx_query, influx_query_tagvalues
from nova.models import *

from core.conf import conf_file

# Defines all possible states of an instance, grouped if is On/Off
to_on_states = [
    'create',
    'restore',
    'start',
    'reboot',
    'unpause',
    'resume',
    'unrescue',
    'unshelve',
    'pause']
to_off_states = [
    'softDelete',
    'forceDelete',
    'delete',
    'stop',
    'shelve',
    'suspend',
    'error']


def aggregate_report():
    """Generate a report with total of resources in used and reserved for
    each aggregate."""

    context = {}

    aggregates = Aggregates.objects.all()
    for aggregate in aggregates:

        # Add aggregate on context dict
        if aggregate.name not in context:
            context[aggregate.name] = {}
            context[aggregate.name]['computes'] = []
            context[aggregate.name]['flavors'] = []

        for service in aggregate.hosts.all():

            # Continue if service are not associate with a hypervisor
            try:
                hypervisor = service.hypervisor
            except BaseException:
                continue
            compute_detail = {}
            compute_detail['name'] = hypervisor.hypervisor_hostname.replace(
                conf_file['billing']['hostname_domain'], '')
            compute_detail['running_vms'] = hypervisor.running_vms
            compute_detail['vcpus_total'] = hypervisor.vcpus
            compute_detail['vcpus_used'] = hypervisor.vcpus_used
            compute_detail['ram_total'] = math.trunc(
                hypervisor.memory_mb / 1024)
            compute_detail['ram_used'] = math.trunc(
                hypervisor.memory_mb_used / 1024)

            # The nova placement could have problems with resources reserved,
            # informing more or fewer resources than truly are available.
            # To fix that, on the memory field, we retrieve from InfluxDB
            # how much memory is free. Note that 'mem.free_mb' metric must
            # be declared on the configuration file, to be collected by Monasca
            end_time = timezone.now()
            start_time = end_time - datetime.timedelta(minutes=15)
            date_influx = influx_query(
                measurement='mem.free_mb',
                resource_name='hostname',
                resource_id=compute_detail['name'],
                begin_date=start_time.isoformat(),
                end_date=end_time.isoformat()
            )

            compute_detail['ram_eff_total'] = compute_detail['ram_total']
            if date_influx:
                compute_detail['ram_eff_used'] = math.trunc(
                    (hypervisor.memory_mb - date_influx[-1]['_value']) / 1024)
            else:
                compute_detail['ram_eff_used'] = compute_detail['ram_used']

            if compute_detail['ram_used'] > compute_detail['ram_eff_used']:
                compute_detail['ram_eff_used'] = compute_detail['ram_used']

            compute_detail['disk_total'] = hypervisor.local_gb
            compute_detail['disk_used'] = hypervisor.local_gb_used

            # save current compute details
            context[aggregate.name]['computes'].append(compute_detail)

        # calculate the percentage of vcpus, ram and effective ram
        for compute in context[aggregate.name]['computes']:
            compute['vcpus_perc'] = math.trunc(
                (compute['vcpus_used'] / compute['vcpus_total']) * 100)
            compute['ram_perc'] = math.trunc(
                (compute['ram_used'] / compute['ram_total']) * 100)
            compute['ram_eff_perc'] = math.trunc(
                (compute['ram_eff_used'] / compute['ram_eff_total']) * 100)

        # compute flavors for current aggregate
        flavors = aggregate.flavors.all()
        for flavor in flavors:
            flavor_detail = {}
            flavor_detail['name'] = flavor.name
            flavor_detail['vcpu'] = flavor.vcpus
            flavor_detail['ram'] = flavor.ram / 1024
            flavor_detail['disk'] = flavor.disk
            flavor_detail['running_vms'] = flavor.servers.exclude(
                status="DELETED").count()

            # checks how many servers could be created from this flavor
            flavors_used = 0
            flavors_total = 0
            for compute in context[aggregate.name]['computes']:
                vcpus_available = math.trunc(
                    compute['vcpus_total'] * 4 - compute['vcpus_used'])
                ram_available = math.trunc(
                    compute['ram_eff_total'] - compute['ram_eff_used'])
                # total
                flavor_vcpus_total = math.trunc(
                    compute['vcpus_total'] * 4 / flavor_detail['vcpu'])
                flavor_ram_total = math.trunc(
                    compute['ram_eff_total'] / flavor_detail['ram'])
                # available
                flavor_vcpus_availability = math.trunc(
                    vcpus_available / flavor_detail['vcpu'])
                flavor_ram_availability = math.trunc(
                    ram_available / flavor_detail['ram'])
                flavors_used += min(flavor_vcpus_availability,
                                    flavor_ram_availability)
                flavors_total += min(flavor_vcpus_total, flavor_ram_total)

            flavor_detail['flavors_available'] = flavors_used
            flavor_detail['flavors_total'] = flavors_total

            # save current flavor details
            context[aggregate.name]['flavors'].append(flavor_detail)

    # create a summary for each aggregate with sum of vcpus and ram
    # besides, the percentage of resources
    for _, aggregate in context.items():
        aggregate["aggregate_summary"] = {
            "vms_used": 0,
            "vcpus_used": 0,
            "vcpus_reserved": 0,
            "ram_used": 0,
            "ram_reserved": 0,
            "ram_eff_used": 0,
            "ram_eff_reserved": 0
        }
        aggregate_summary = aggregate["aggregate_summary"]

        for compute in aggregate['computes']:
            aggregate_summary["vms_used"] += compute["running_vms"]
            aggregate_summary["vcpus_used"] += compute["vcpus_used"]
            aggregate_summary["vcpus_reserved"] += compute["vcpus_total"]
            aggregate_summary["ram_used"] += compute["ram_used"]
            aggregate_summary["ram_reserved"] += compute["ram_total"]
            aggregate_summary["ram_eff_used"] += compute["ram_eff_used"]
            aggregate_summary["ram_eff_reserved"] += compute["ram_eff_total"]

        aggregate_summary["vcpus_perc"] = _perc_validate_zero_division(
            aggregate_summary["vcpus_used"], aggregate_summary["vcpus_reserved"])
        aggregate_summary["ram_perc"] = _perc_validate_zero_division(
            aggregate_summary["ram_used"], aggregate_summary["ram_reserved"])
        aggregate_summary["ram_eff_perc"] = _perc_validate_zero_division(
            aggregate_summary["ram_eff_used"], aggregate_summary["ram_eff_reserved"])

    return context


def _summary_capacity_report():
    """Process the cloud capacity."""

    # used
    used_vcpus = Servers.objects.exclude(
        status="DELETED").aggregate(
        sum=Sum('flavor__vcpus'))['sum']
    used_ram = Servers.objects.exclude(
        status="DELETED").aggregate(
        sum=Sum('flavor__ram'))['sum'] / 1024
    used_fips = ProjectQuotas.objects.aggregate(
        sum=Sum('floatingip_used'))['sum']
    used_volumes_size = Volumes.objects.aggregate(sum=Sum('size'))['sum']

    # quota
    quota_vcpus = ProjectQuotas.objects.aggregate(sum=Sum('cores'))['sum']
    quota_ram = ProjectQuotas.objects.aggregate(sum=Sum('ram'))['sum'] / 1024
    quota_fips = ProjectQuotas.objects.aggregate(
        sum=Sum('floatingip_limit'))['sum']
    quota_volumes_size = ProjectQuotas.objects.aggregate(sum=Sum('gigabytes'))[
        'sum']

    # capacity
    capacity_vcpus = Hypervisors.objects.aggregate(sum=Sum('vcpus'))['sum'] * 4
    capacity_ram = Hypervisors.objects.aggregate(
        sum=Sum('memory_mb'))['sum'] / 1024
    capacity_fips = "-"
    capacity_volumes_size = "-"

    # real_capacity
    real_capacity_vcpus = Hypervisors.objects.aggregate(sum=Sum('vcpus'))['sum']
    real_capacity_ram = Hypervisors.objects.aggregate(sum=Sum('memory_mb'))[
        'sum'] / 1024
    real_capacity_fips = "-"
    real_capacity_volumes_size = "-"

    capacity = {
        "used": {
            "vcpus": f"{used_vcpus} ({used_vcpus/capacity_vcpus*100:.2f}%)",
            "ram": f"{used_ram:.0f} ({used_ram/capacity_ram*100:.2f}%)",
            "fips": f"{used_fips} (?)",
            "volumes_size": f"{used_volumes_size} (?)",
        },
        "quota": {
            "vcpus": f"{quota_vcpus} ({quota_vcpus/capacity_vcpus*100:.2f}%)",
            "ram": f"{quota_ram:.0f} ({quota_ram/capacity_ram*100:.2f}%)",
            "fips": f"{quota_fips} (?)",
            "volumes_size": f"{quota_volumes_size} (?)",
        },
        "capacity": {
            "vcpus": f"{capacity_vcpus}",
            "ram": f"{capacity_ram:.0f}",
            "fips": f"{capacity_fips}",
            "volumes_size": f"{capacity_volumes_size}",
        },
        "real_capacity": {
            "vcpus": f"{real_capacity_vcpus}",
            "ram": f"{real_capacity_ram:.0f}",
            "fips": f"{real_capacity_fips}",
            "volumes_size": f"{real_capacity_volumes_size}",
        }
    }

    return capacity


def human_readable_size(size, decimal_places=3):
    """Return human storage size."""

    for unit in ['B','KiB','MiB','GiB','TiB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

def _summary_ceph_report():
    ceph_report = []

    pools = influx_query_tagvalues('pool')

    measurementes_values = [
          'ceph.pool.max_avail_bytes',
          'ceph.pool.used_bytes',
          'ceph.pool.total_bytes',
          'ceph.pool.used_raw_bytes',
        ]

    for pool in pools:
        pool_detail = {'name': pool}
        for measurement in measurementes_values:
            measurement_value = influx_query(
                measurement=measurement,
                resource_name='pool',
                resource_id=pool,
                begin_date='-3h',
            )

            # rename measurement name
            measurement = measurement.split('.')[-1]
            if (measurement_value):
                pool_detail[measurement] = human_readable_size(measurement_value[0]['_value'],2)
            else:
                pool_detail[measurement] = "-"

        ceph_report.append(pool_detail)

    return ceph_report


def _summary_sponsors_report():
    """Process all sponsors usage."""

    end_date = timezone.now()
    begin_date = end_date - datetime.timedelta(days=30)
    sponsors = sponsors_report(begin_date.isoformat(), end_date.isoformat())

    summary = {}

    for sponsor in sponsors:
        if sponsor not in summary.keys():
            summary[sponsor] = {
                "projects": [],
                "total": {
                    "vcpu_hours": 0,
                    "ram_hours": 0,
                    "vms": 0,
                    "vcpus": 0,
                    "ram": 0,
                    "disk": 0,
                    "fips": 0,
                    "lbs": 0,
                    "cpu_avg": 0,
                    "mem_avg": 0,
                }
            }

        for project in sponsors[sponsor]:
            details = {}
            details["name"] = project['header']['project']
            details["vcpu_hours"] = project['header']['total_used_vcpu']
            details["ram_hours"] = project['header']['total_used_mem']
            details["cpu_avg"] = project['header']['total_cpu_avg']
            details["mem_avg"] = project['header']['total_mem_avg']
            for resource in project['body']['resources']:
                if resource['name'] == "Instâncias":
                    details["vms"] = resource['used']
                    details["vms_used_perc"] = resource['perc_used']
                elif resource['name'] == "vCPU":
                    details["vcpus"] = resource['used']
                    details["vcpus_used_perc"] = resource['perc_used']
                elif resource['name'] == "RAM (GB)":
                    details["ram"] = resource['used']
                    details["ram_used_perc"] = resource['perc_used']
                elif resource['name'] == "Armazenamento (GB)":
                    # sum volumes with the root disk from servers
                    details["disk"] = resource['used'] + Projects.objects.get(
                        name=project['header']['project']).servers.aggregate(
                        sum=Coalesce(Sum("flavor__disk"), Value(0)))['sum']
                    details["disk_used_perc"] = resource['perc_used']
                elif resource['name'] == "IPs Flutuante":
                    details["fips"] = resource['used']
                    details["fips_used_perc"] = resource['perc_used']
                elif resource['name'] == "Load Balancers":
                    details["lbs"] = resource['used']
                    details["lbs_used_perc"] = resource['perc_used']

            summary[sponsor]['projects'].append(details)

        for project in summary[sponsor]['projects']:
            summary[sponsor]['total']["vcpu_hours"] += project["vcpu_hours"]
            summary[sponsor]['total']["ram_hours"] += project["ram_hours"]
            summary[sponsor]['total']["vms"] += project["vms"]
            summary[sponsor]['total']["vcpus"] += project["vcpus"]
            summary[sponsor]['total']["ram"] += project["ram"]
            summary[sponsor]['total']["disk"] += project["disk"]
            summary[sponsor]['total']["fips"] += project["fips"]
            summary[sponsor]['total']["lbs"] += project["lbs"]
            summary[sponsor]['total']["cpu_avg"] += project["cpu_avg"] * \
                project["vms"]
            summary[sponsor]['total']["mem_avg"] += project["mem_avg"] * \
                project["vms"]

        # avoid division by zero
        n_vms = summary[sponsor]['total']["vms"] if summary[sponsor]['total']["vms"] else 1

        summary[sponsor]['total']["cpu_avg"] = round(
            summary[sponsor]['total']["cpu_avg"] / n_vms, 2)
        summary[sponsor]['total']["mem_avg"] = round(
            summary[sponsor]['total']["mem_avg"] / n_vms, 2)

    return summary


def summary_report():
    """Generate a report with total of resources in used and reserved for
    each aggregate.

    context = {
        "capacity": {
            "used": {
                "vcpus": "200 (30%)",
                "ram": "500 (50%)",
                "fips": "200 (30%)",
                "volumes_size": "200 (30%)",
            },
            "quota": {
                "vcpus": "200 (30%)",
                "ram": "500 (50%)",
                "fips": "200 (30%)",
                "volumes_size": "200 (30%)",
            },
            "capacity": {
                "vcpus": "200 (30%)",
                "ram": "500 (50%)",
                "fips": "200 (30%)",
                "volumes_size": "200 (30%)",
            },
            "real_capacity": {
                "vcpus": "200 (30%)",
                "ram": "500 (50%)",
                "fips": "200 (30%)",
                "volumes_size": "200 (30%)",
            }
        },
        "ceph": [
            {
                "pool": "name",
                "available": "2.7 TiB",
                "used": "6.93 TiB",
                "total": "9.66 TiB",
                "raw": "13.94 TiB",
            },
            {
                "pool": "name",
                "available": "2.7 TiB",
                "used": "6.93 TiB",
                "total": "9.66 TiB",
                "raw": "13.94 TiB",
            }
        ],
        "sponsors": [
            {
                "name": "sponsor@mail.com",
                "projects": [
                    {
                        "name": "project_name",
                        "vcpu_hours": 10000,
                        "ram_hours": 10000,
                        "vms": 10000,
                        "vcpus": 10000,
                        "ram": 10000,
                        "disk": 10000,
                        "fips": 10000,
                        "lbs": 10000,
                        "cpu_perc": 28.59,
                        "ram_perc": 14.50,
                    }
                ],
                "total": {
                    "vcpu_hours": 10000,
                    "ram_hours": 10000,
                    "vms": 10000,
                    "vcpus": 10000,
                    "ram": 10000,
                    "disk": 10000,
                    "fips": 10000,
                    "lbs": 10000,
                    "cpu_perc": 28.59,
                    "ram_perc": 14.50,
                }
            }
        ]
    }
    """

    context = {
        "capacity": _summary_capacity_report(),
        "ceph": _summary_ceph_report(),
        "sponsors": _summary_sponsors_report(),
    }

    return context


def sponsors_report(begin_date: str, end_date: str):
    """Generate a report with details about all projects for each sponsor.

    :param begin_date: date string in iso format like 2021-01-31T00:00:00-03:00
    :param end_date: date string in iso format like 2021-01-31T00:00:00-03:00
    :returns: a dict with the following format:
            context = {
                "sponsor1" : {
                    "header": {...}
                    "body": {
                        resources: {...},
                        "servers": {...},
                        "volumes": {...},
                        "flavors": {...}
                    }
                },
                "sponsor2" : {
                    "header": {...}
                    "body": {
                        resources: {...},
                        "servers": {...},
                        "volumes": {...},
                        "flavors": {...}
                    }
                },
                ...
            }
    """

    year = begin_date.split('-')[0]
    month = begin_date.split('-')[1]
    context = {}

    sponsors = Sponsors.objects.all()
    for sponsor in sponsors:
        print(sponsor.email)
        if sponsor.email not in context.keys():
            context[sponsor.email] = []
        projects = sponsor.projects.filter(enabled=True)
        for project in projects:
            # create an dict with project content
            details = {}
            details['header'] = {}
            details['header']['month'] = "%s/%s" % (month, year)
            details['header']['total_cpu_avg'] = 0
            details['header']['total_mem_avg'] = 0
            details['header']['total_used_vcpu'] = 0
            details['header']['total_used_mem'] = 0
            details['header']['domain'] = project.domain_id.name
            details['header']['project'] = project.name
            details['body'] = {}
            # resources
            # project is too recently but dont have quotas, we just skip
            try:
                project_quotas = project.quotas.all()[0]
            except BaseException:
                continue
            nova_servers = project.servers.filter(created__lte=end_date)
            cinder_volumes = project.volumes.filter(created_at__lte=end_date)
            details['body']['resources'] = []
            # instances
            resource_detail = {}
            resource_detail["name"] = "Instâncias"
            resource_detail["used"] = nova_servers.count()
            resource_detail["reserved"] = project_quotas.instances if project_quotas.instances > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # vcpu
            resource_detail = {}
            resource_detail["name"] = "vCPU"
            # sum all vcpus from a queryset of servers
            resource_detail["used"] = nova_servers.aggregate(
                sum=Coalesce(Sum('flavor__vcpus'), 0))['sum']
            resource_detail["reserved"] = project_quotas.cores if project_quotas.cores > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # ram
            resource_detail = {}
            resource_detail["name"] = "RAM (GB)"
            # sum all ram from a queryset of servers
            resource_detail["used"] = math.trunc(
                nova_servers.aggregate(
                    sum=Coalesce(
                        Sum('flavor__ram'),
                        1))['sum'] / 1024)
            resource_detail["reserved"] = math.trunc(
                project_quotas.ram / 1024) if project_quotas.ram > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # storage
            resource_detail = {}
            resource_detail["name"] = "Armazenamento (GB)"
            volumes_storage_used = cinder_volumes.aggregate(
                sum=Coalesce(Sum('size'), 0))['sum']
            backups_storage_used = cinder_volumes.aggregate(
                sum=Coalesce(Sum('backup__size'), 0))['sum']
            snapshots_storage_used = cinder_volumes.aggregate(
                sum=Coalesce(Sum('snapshot_id__size'), 0))['sum']
            resource_detail["used"] = volumes_storage_used + \
                backups_storage_used + snapshots_storage_used
            resource_detail["reserved"] = project_quotas.gigabytes if project_quotas.gigabytes > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # volumes
            resource_detail = {}
            resource_detail["name"] = "Volumes"
            resource_detail["used"] = cinder_volumes.count()
            resource_detail["reserved"] = project_quotas.volumes if project_quotas.volumes > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # backups
            resource_detail = {}
            resource_detail["name"] = "Backups"
            resource_detail["used"] = cinder_volumes.aggregate(
                sum=Coalesce(Count('backup'), 0))['sum']
            resource_detail["reserved"] = project_quotas.volumes if project_quotas.volumes > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # snapshots
            resource_detail = {}
            resource_detail["name"] = "Snapshots de volume"
            resource_detail["used"] = cinder_volumes.aggregate(
                sum=Coalesce(Count('snapshot_id'), 0))['sum']
            resource_detail["reserved"] = project_quotas.backups if project_quotas.backups > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # load balancer
            resource_detail = {}
            resource_detail["name"] = "Load Balancers"
            resource_detail["used"] = project_quotas.loadbalancer_used
            resource_detail["reserved"] = project_quotas.loadbalancer_limit if project_quotas.loadbalancer_limit > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # floating ip
            resource_detail = {}
            resource_detail["name"] = "IPs Flutuante"
            resource_detail["used"] = project_quotas.floatingip_used
            resource_detail["reserved"] = project_quotas.floatingip_limit if project_quotas.floatingip_limit > 0 else 1
            resource_detail["perc_used"] = round(
                (resource_detail["used"] / resource_detail["reserved"]) * 100, 2)
            details['body']['resources'].append(resource_detail)
            # servers
            details['body']['servers'] = []
            for server in nova_servers:
                begin_datetime = datetime.datetime.fromisoformat(begin_date)
                end_datetime = datetime.datetime.fromisoformat(end_date)

                resource_detail = {}
                resource_detail["name"] = server.name
                resource_detail["flavor"] = server.flavor.name
                # calculate hours used
                resource_detail["hours_used"] = int(
                    math.ceil(
                        _instance_uptime(
                            server,
                            begin_datetime,
                            end_datetime).total_seconds() /
                        60 /
                        60))
                # skip this billing because exist bug on our openstack
                if resource_detail["hours_used"] == 0:
                    continue

                # build status through actions
                server_status_action = server.actions.values()
                if server_status_action:
                    server_status_action = server_status_action[0]
                    if server_status_action == "pause":
                        resource_detail["status"] = "Ativa (pausada)"
                    elif server_status_action in to_off_states:
                        resource_detail["status"] = "Inativa"
                    elif server_status_action not in to_off_states:
                        resource_detail["status"] = "Ativa"
                else:
                    resource_detail["status"] = "Indefinido"
                # calculate cpu usage
                measurement = "vm.cpu.utilization_norm_perc"
                resource_name = "resource_id"
                resource_id = server.id
                cpu_records = influx_query(
                    measurement=measurement,
                    resource_name=resource_name,
                    resource_id=resource_id,
                    begin_date=begin_date,
                    end_date=end_date,
                    aggregate_day=True)
                if cpu_records:
                    cpu_avg = 0
                    for cpu in cpu_records:
                        cpu_avg += cpu['_value']
                    resource_detail["cpu_avg"] = round(
                        cpu_avg / len(cpu_records), 2)
                else:
                    resource_detail["cpu_avg"] = "-"

                # memory
                measurement = "vm.mem.free_perc"
                resource_name = "resource_id"
                resource_id = server.id
                mem_records = influx_query(
                    measurement=measurement,
                    resource_name=resource_name,
                    resource_id=resource_id,
                    begin_date=begin_date,
                    end_date=end_date,
                    aggregate_day=True)
                if mem_records:
                    mem_avg = 0
                    for mem in mem_records:
                        mem_avg += mem['_value']
                    resource_detail["mem_avg"] = round(
                        100 - (mem_avg / len(mem_records)), 2)
                else:
                    resource_detail["mem_avg"] = "-"
                details['body']['servers'].append(resource_detail)

            # volumes used
            details['body']['volumes'] = []
            for volume in cinder_volumes:
                resource_detail = {}
                if volume.name != "":
                    resource_detail['name'] = volume.name
                else:
                    resource_detail['name'] = volume.id
                resource_detail['size'] = volume.size
                details['body']['volumes'].append(resource_detail)

            # flavors used
            flavors_list = []
            for server in nova_servers:
                if server.flavor not in flavors_list:
                    flavors_list.append(server.flavor)
            flavors_list = sorted(flavors_list, key=lambda x: x.vcpus)
            details['body']['flavors'] = []
            for flavor in flavors_list:
                resource_detail = {}
                resource_detail['name'] = flavor.name
                resource_detail['vcpus'] = flavor.vcpus
                resource_detail['mem_gb'] = math.trunc(flavor.ram / 1024)
                resource_detail['disk_size'] = flavor.disk
                details['body']['flavors'].append(resource_detail)

            # calculate amount of used hours in GB and vcpu
            for server in details['body']['servers']:
                for flavor in details['body']['flavors']:
                    if server['flavor'] == flavor['name']:
                        details['header']['total_used_vcpu'] += server['hours_used'] * \
                            flavor['vcpus']
                        details['header']['total_used_mem'] += server['hours_used'] * \
                            flavor['mem_gb']

                # sum all percentage of vcpu used by server
                if server['cpu_avg'] == "-":
                    details['header']['total_cpu_avg'] += 0
                else:
                    details['header']['total_cpu_avg'] += server['cpu_avg']
                # sum all percentage of mem used by server
                if server['mem_avg'] == "-":
                    details['header']['total_mem_avg'] += 0
                else:
                    details['header']['total_mem_avg'] += server['mem_avg']
            # cpu
            details['header']['total_cpu_avg'] = _perc_validate_zero_division(
                details['header']['total_cpu_avg'] / 100, len(details['body']['servers']), round_result=True)
            # mem
            details['header']['total_mem_avg'] = _perc_validate_zero_division(
                details['header']['total_mem_avg'] / 100, len(details['body']['servers']), round_result=True)

            context[sponsor.email].append(details)

    return context


def _perc_validate_zero_division(
        numerator: int, denominator: int, round_result=False):
    """Return a division, treating the problem when denominator is zero."""

    if denominator == 0:
        return numerator
    if round_result:
        return round((numerator / denominator) * 100, 2)
    return math.trunc((numerator / denominator) * 100)


def _instance_uptime(server, start_date: datetime, end_date: datetime):
    """Calculate the total uptime of an instance based on status of Nova Compute."""

    total = datetime.timedelta(days=0)
    on = False
    last = start_date

    for action in server.actions.all().order_by('start_time'):
        date = action.start_time

        if date > end_date:
            break

        if date >= start_date:
            if on:
                total += date - last
            last = date

        if action.action not in to_off_states:
            on = True
        elif action.action in to_off_states:
            on = False

    if on:
        total += end_date - last

    return total


def write_report(context: str, template_name: str, report_type: str):
    """Write report in a Jinja template.

    :param context: a list of dicts with the data formated
    :param template_name: name of Jinja template. must be on templates path
    :returns: a list of dicts, with the reports as io.Bytes
              [
                  {
                      "type": aggregate | sponsor
                      "id": "sponsor@mail.com" | "aggregates"
                      "report": io.Bytes
                  }
                  ...
              ]
    """

    reports = []
    if report_type == "aggregate":
        # Add the context key on dict, where Jinja will iterate to write
        new_context = {'context': context}
        tmp_report = {"type": report_type, "id": "aggregates"}
        tmp_report["report"] = io.BytesIO()
        content = render_to_string(template_name, new_context)
        tmp_report["report"].write(content.encode())
        reports.append(tmp_report)
    elif report_type == "summary":
        # Add the context key on dict, where Jinja will iterate to write
        new_context = {'context': context}
        tmp_report = {"type": report_type, "id": "summary"}
        tmp_report["report"] = io.BytesIO()
        content = render_to_string(template_name, new_context)
        tmp_report["report"].write(content.encode())
        reports.append(tmp_report)
    elif report_type == "sponsor":
        for sponsor in context:
            # Skip sponsors who do not have projects.
            if not context[sponsor]:
                continue

            # Add the context key on dict, where Jinja will iterate to write.
            new_context = {'context': context[sponsor]}
            tmp_report = {"type": report_type, "id": sponsor}
            tmp_report["report"] = io.BytesIO()
            content = render_to_string(template_name, new_context)
            tmp_report["report"].write(content.encode())
            reports.append(tmp_report)

    return reports


def persists_reports(filename: str, report: io.BytesIO):
    """Saves a report in default storage, the file system of Django.

    :param report: io.BytesIO with the .html to be persisted.
    :param filename: name of file, including directories.
    """

    return default_storage.save(filename, report)


def send_report_by_email(html_report: dict, subject: str,
                         source_email: str, target_email: str):
    """Send a .html report to an email.

    :param report: io.BytesIO with the .html to be sended.
    :param email: target where report will be sended.
    """

    from django.core import mail
    from django.utils.html import strip_tags

    plain_message = strip_tags(html_report)
    mail.send_mail(
        subject, plain_message, source_email, [target_email], html_message=html_report)
