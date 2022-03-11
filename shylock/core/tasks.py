import calendar
import datetime

from decouple import config
from pytz import timezone

from celery import shared_task
from core.conf import conf_file
from core.manager import (aggregate_report, persists_reports,
                          send_report_by_email, sponsors_report, write_report)


def _generate_date_range_last_month():
    """Build a range datetime for begin and end of the last month.

    :return: datetime in isoformat.
    """

    local_timezone = conf_file['billing']['timezone']
    today = datetime.date.today()

    # Go to the first day of the month and return to the last day
    # of the last month.
    end_last_month = today
    begin_last_month = end_last_month.replace(day=1)

    begin_last_month = datetime\
        .datetime\
        .combine(
            begin_last_month,
            datetime.time.min,
            tzinfo=timezone(local_timezone))
    end_last_month = datetime\
        .datetime\
        .combine(
            end_last_month,
            datetime.time.max,
            tzinfo=timezone(local_timezone))\
        .replace(microsecond=0)

    return [begin_last_month.isoformat(), end_last_month.isoformat()]


@shared_task
def generate_sponsors_report(send_email: bool = None):
    """Generate sponsors reports, save on disk and could send email.

    :param send_email: if true, generate report and send to sponsor by email.
    """

    begin_date, end_date = _generate_date_range_last_month()

    # Retrieve the reports and write the templates.
    context = sponsors_report(begin_date=begin_date, end_date=end_date)
    aggregate_bytes = write_report(
        context, 'user_report_template.html', 'sponsor')

    for report_bytes in aggregate_bytes:
        today = datetime.date.today()
        filename = "sponsors/%s_%s_%s_%s.html" % (
            today.year, today.month, today.day, report_bytes['id'])
        report_bytes['report'].seek(0)
        persists_reports(filename, report_bytes['report'])

        if send_email:
            report_bytes['report'].seek(0)
            content = report_bytes['report'].read()
            send_report_by_email(
                html_report=content.decode(),
                subject=conf_file['billing']['sponsors']['email_subject'],
                source_email=config("EMAIL_FROM_EMAIL"),
                target_email=conf_file['billing']['operators']['mail'])
            # TODO must change the target email to sponsor.
            # This is a secure lock, in code, to guarantee that emails 
            # are not be sended by sponsors as mistake.


@shared_task
def generate_aggregates_report(send_email: bool = None):
    """Generate aggregate report, save on disk and could send by email.

    :param send_email: if true, generate report and send to operators by email.
    """

    context = aggregate_report()
    aggregate_bytes = write_report(
        context, 'aggregates_report_template.html', 'aggregate')
    today = datetime.datetime.now()

    for report_bytes in aggregate_bytes:
        filename = "aggregates/%s_%s_%s_aggregate.html" % (
            today.year, today.month, today.day)
        report_bytes['report'].seek(0)
        persists_reports(filename, report_bytes['report'])

        if send_email:
            report_bytes['report'].seek(0)
            content = report_bytes['report'].read()
            send_report_by_email(
                html_report=content.decode(),
                subject=conf_file['billing']['operators']['email_subject'],
                source_email=config("EMAIL_FROM_EMAIL"),
                target_email=conf_file['billing']['operators']['mail'])
