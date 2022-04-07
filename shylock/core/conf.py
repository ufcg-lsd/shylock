import yaml


def validate_conf(yaml_path: str) -> dict:
    """Validate if conf file is valid and return dict."""

    with open(yaml_path, 'r') as file:
        conf_file = yaml.safe_load(file)

    billing = conf_file.get('billing')
    openstack = conf_file.get('openstack')
    monasca = conf_file.get('monasca')
    if not (billing or openstack or monasca):
        raise Exception('Conf file not valid.')

    monasca_statistics = monasca.get('statistics')
    if not monasca_statistics:
        raise Exception('Conf file not valid.')

    for statistic in monasca_statistics:
        monasca_statistics_name = statistic.get('name')
        monasca_statistics_type = statistic.get('type')
        monasca_statistics_dimensions = statistic.get('dimensions')
        monasca_statistics_filter_by = statistic.get('filter_by')
        monasca_statistics_period = statistic.get('period')
        if not (monasca_statistics_name or monasca_statistics_type or monasca_statistics_dimensions or
                monasca_statistics_filter_by or monasca_statistics_period):
            raise Exception('Conf file not valid.')

    return conf_file


conf_file = validate_conf('./conf.yaml')
