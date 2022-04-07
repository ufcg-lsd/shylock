import datetime

from celery import shared_task
from core.conf import conf_file
from decouple import config
from django.conf import settings
from django.utils.timezone import now
from monascaclient import client as monasca_client
from nova.models import Hypervisors, Servers

monasca = monasca_client.Client(
    api_version=config("MONASCA_API_VERSION"),
    session=settings.OPENSTACK_SESSION,
    endpoint=config("MONASCA_ENDPOINT"),
    interface=config("MONASCA_INTERFACE"),
)


def influx_query(measurement, resource_name, resource_id,
                 begin_date=None, end_date=None):
    """Wrapper to query points on InfluxDB."""

    bucket_name = config("INFLUX_BUCKET")
    # retrieve points from last 30 days
    if not begin_date:
        begin_date = '-30d'
    if not end_date:
        end_date = datetime.datetime.now().isoformat() + 'Z'
    from_bucket = ('from(bucket:"%s")' % bucket_name)
    date_range = (' |> range(start: %s, stop: %s)' % (begin_date, end_date))
    filter_measurement = (
        ' |> filter(fn:(r) => r._measurement == "%s")' %
        measurement)
    filter_resource = (
        ' |> filter(fn:(r) => r.%s == "%s")' %
        (resource_name, resource_id))

    query = from_bucket + date_range + filter_measurement + filter_resource
    # query points
    points = settings.INFLUX_CLIENT.query_api().query(query)

    # parser the points to list
    result = []
    for table in points:
        for row in table.records:
            result.append(row.values)

    return result


@shared_task
def schedule_save_statistics() -> None:
    """Collect all metrics declared in yaml configuration file."""

    for statistic_definition in conf_file['monasca']['statistics']:
        resource_name = statistic_definition['dimension']

        if resource_name == "resource_id":
            resource_objects = Servers.objects.all().values()
        elif resource_name == "hostname":
            resource_objects = Hypervisors.objects.all().values()

        for resource in resource_objects:
            save_statistics.delay(statistic_definition, resource_name, resource)


@shared_task
def save_statistics(statistics_dict, resource_name, resource):
    """Save a statistic from Monasca on InfluxDB."""

    statistics_parsed = []

    for statistic_name in statistics_dict['name']:
        if resource_name == "hostname":
            # The hostname in OpenStack can follow the name of the domain
            # to which the resource is tied, the line below removes the name
            # of that domain
            resource['id'] = resource['hypervisor_hostname'].replace(
                conf_file['billing']['hostname_domain'], '')

        date_influx = influx_query(
            measurement=statistic_name,
            resource_name=resource_name,
            resource_id=str(resource['id'])
        )
        if not date_influx:
            start_date = now() - datetime.timedelta(days=1)
        else:
            start_date = date_influx[-1]['_time']

        # define which metrics must be saved
        dimensions = {
            resource_name: str(resource['id'])
        }
        metric_type = statistics_dict['type']
        start_time = start_date.isoformat(' ', 'seconds')
        end_time = now().isoformat(' ', 'seconds')
        period = statistics_dict['period']

        statistics = monasca.metrics.list_statistics(
            name=statistic_name,
            dimensions=dimensions,
            statistics=metric_type,
            start_time=start_time,
            end_time=end_time,
            period=period,
            merge_metrics=True
        )

        if not len(statistics):
            print('Not Found')
            continue

        # monasca returned
        statistics = statistics[0]
        for statistic in statistics['statistics']:
            statistic_point = {}
            statistic_point['measurement'] = statistics['name']
            statistic_point['tags'] = statistics['dimensions']
            statistic_point['fields'] = {}
            statistic_point['fields']['value'] = float(statistic[1])
            statistic_point['time'] = statistic[0]
            statistics_parsed.append(statistic_point)

    # write on InfluxDB
    settings.INFLUX_CLIENT.write_api().write(
        bucket=config("INFLUX_BUCKET"), record=statistics_parsed)
