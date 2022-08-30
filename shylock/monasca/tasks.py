import datetime

from celery import shared_task
from core.conf import conf_file
from decouple import config
from django.conf import settings
from django.utils.timezone import now
from monascaclient import client as monasca_client
from nova.models import Hypervisors, Servers
from pytz import timezone

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
            backward_force = conf_file['monasca'].get('backward_force', False)
            if backward_force:
                resource_objects = Servers.objects.all().values()
            else:
                resource_objects = Servers.objects.exclude(
                    status="DELETED").values()
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
        # force to go backwar even when already exists data on InfluxDB
        backward_force = conf_file['monasca'].get('backward_force', False)
        if backward_force:
            # build begin date when user wants force retrieve backward data
            begin_date = datetime.datetime.strptime(
                conf_file['monasca']['backward_date'], '%d/%m/%Y')
            begin_date = begin_date.astimezone(timezone('UTC'))
            backward_days = (now() - begin_date).days
            start_date = datetime.datetime(
                now().year, now().month, now().day, 0, 0, 0)
            start_date = start_date - datetime.timedelta(days=backward_days)
        elif not date_influx:
            # default value is 1 day
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

        if backward_force:
            # the monasca limits the number os statistics
            # we strike the endpoint N times from begin of backward date
            # until the difference between from last statistic and current
            # date is less than 1 day

            # the buffer with statistics from beginning until end time
            statistics_buffer = []
            # when the loop will stop
            condition = end_time
            max_curr = 0
            # number of times we gonna hit the endpoint before get out
            max_retries = conf_file['monasca']['backward_max_retries']
            while condition:
                # get out from main loop to avoid deadlock
                if max_curr == max_retries:
                    break
                # request inside a loop to can retry when API fails
                while max_curr != max_retries:
                    try:
                        statistics = monasca.metrics.list_statistics(
                            name=statistic_name,
                            dimensions=dimensions,
                            statistics=metric_type,
                            start_time=start_time,
                            end_time=end_time,
                            period=period,
                            merge_metrics=True
                        )
                        break
                    except Exception as error:
                        max_curr += 1
                        print(error)
                        continue
                # main condition to stop the requests on endpoint
                condition = (now() - datetime.datetime.strptime(
                    statistics[0]['statistics'][-1][0], '%Y-%m-%dT%H:%M:%SZ').astimezone(timezone('UTC'))).days > 0
                # merge the statistics with the buffer
                statistics_buffer += statistics[0]['statistics']
                # validate if the new start_time is different from before
                # this avoid deadlock when retrieve statistics from a DELETED
                # server, where he cant satisfy the main condition for get out
                new_start_time = datetime.datetime.strptime(
                    statistics[0]['statistics'][-1][0], '%Y-%m-%dT%H:%M:%SZ')
                if new_start_time == start_time:
                    break
                # replace the start_time always when retrieve new statistics
                start_time = new_start_time
        else:
            statistics = monasca.metrics.list_statistics(
                name=statistic_name,
                dimensions=dimensions,
                statistics=metric_type,
                start_time=start_time,
                end_time=end_time,
                period=period,
                merge_metrics=True
            )
            statistics_buffer = statistics[0]['statistics']

        # replace current statistics to the buffered
        # this works when backward_force are enabled, otherwise
        # the operation is idempotent
        statistics[0]['statistics'] = statistics_buffer

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
