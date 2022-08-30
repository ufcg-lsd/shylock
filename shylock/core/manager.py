import datetime
import io
import math

from cinder.models import *
from django.core.files.storage import default_storage
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone
from keystone.models import *
from monasca.tasks import influx_query, monasca
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
        if sponsor.email not in context.keys():
            context[sponsor.email] = []
        projects = sponsor.projects.all()
        for project in projects:
            print(project)
            # create an dict with project content
            details = {}
            details['header'] = {}
            details['header']['month'] = "%s/%s" % (month, year)
            details['header']['total_cpu_avg'] = 0
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
                    end_date=end_date)
                if cpu_records:
                    cpu_avg = 0
                    for cpu in cpu_records:
                        cpu_avg += cpu['_value']
                    resource_detail["cpu_avg"] = round(
                        cpu_avg / len(cpu_records), 2)
                else:
                    resource_detail["cpu_avg"] = 0
                details['body']['servers'].append(resource_detail)

            # volumes used
            details['body']['volumes'] = []
            for volume in cinder_volumes:
                resource_detail = {}
                resource_detail['name'] = volume.name
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
                details['header']['total_cpu_avg'] += server['cpu_avg']
            details['header']['total_cpu_avg'] = _perc_validate_zero_division(
                details['header']['total_cpu_avg'] / 100, len(details['body']['servers']), round_result=True)

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
