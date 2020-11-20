#!/usr/bin/env python3.7
import json, argparse
from subprocess import getoutput as go

class Scraper:

	def __init__(self):
		pass

parser = argparse.ArgumentParser()
parser.add_argument("--start_date", help="Enter the start date in format year-month-day")
parser.add_argument("--end_date", help="Enter the end date in format year-month-day")
args = parser.parse_args()

#Year-Month-Day
start_date = args.start_date
end_date = args.end_date

go("mkdir reports")
go("mkdir reports/%s-%s" % (start_date.split("-")[1], start_date.split("-")[0]))

domains = {}

instances_number = 0
for domain in go("openstack domain list -f value -c Name").split("\n"):
	domains[domain] = {}
	project_query = "openstack  project list --domain %s -f json" % domain
	print(project_query)
	for project in json.loads(go(project_query)):
		
		volume_query = "openstack volume list --project %s -f json" % project["Name"]
		print(volume_query)
		volume = json.loads(go(volume_query))
		project["Volume"] =  volume
		project["Instances"] = {}
		project["Flavors"] = {}

		project["Abnormal_Instances"] = []

		for instance in json.loads(go("openstack server list --project-domain %s --project %s -f json" % (domain, project["Name"]))):
			project["Instances"][instance["ID"]] =  instance
			project["Instances"][instance["ID"]]["Log"]  = go("nova instance-action-list %s" % instance["ID"])
			bash_instance_name = instance["Name"].replace(" ", "\ ").replace("(", "\(").replace(")", "\)")
			monasca_query = "monasca metric-statistics cpu.utilization_norm_perc --dimensions resource_id=%s,hostname=%s AVG %s --endtime %s --period 900 -j" % (instance["ID"], bash_instance_name, start_date, end_date)
			print(monasca_query)
			project["Instances"][instance["ID"]]["Cpu_Usage_List"] = json.loads(go(monasca_query))
			flavor_query = "openstack flavor show %s -f json" % instance["Flavor"]
			print(flavor_query)
			if instance["Flavor"].strip() == "":
				project["Abnormal_Instances"].append(instance)
				del project["Instances"][instance["ID"]]
			else:
				project["Flavors"][instance["Flavor"]] = json.loads(go(flavor_query))
			instances_number += 1
			print(instances_number)

		for deleted_instance in json.loads(go("openstack server list --project-domain %s --project %s --changes-since %s --deleted -f json" % (domain, project["Name"], start_date))):
			project["Instances"][deleted_instance["ID"]] = deleted_instance
			project["Instances"][deleted_instance["ID"]]["Log"] = go("nova instance-action-list %s" % deleted_instance["ID"])
			bash_instance_name = deleted_instance["Name"].replace(" ", "\ ").replace("(", "\(").replace(")", "\)")
			monasca_query = "monasca metric-statistics cpu.utilization_norm_perc --dimensions resource_id=%s,hostname=%s  AVG %s --endtime %s --period 900 -j" % (deleted_instance["ID"], bash_instance_name,start_date, end_date)
			print(monasca_query)
			project["Instances"][deleted_instance["ID"]]["Cpu_Usage_List"] = json.loads(go(monasca_query))	
			flavor_query = "openstack flavor show %s -f json" % deleted_instance["Flavor"]
			print(flavor_query)
			if deleted_instance["Flavor"].strip() == "":
				project["Abnormal_Instances"].append(deleted_instance)
				del project["Instances"][deleted_instance["ID"]]
			else:
				project["Flavors"][deleted_instance["Flavor"]] = json.loads(go(flavor_query))
			instances_number += 1
			print(instances_number)
		domains[domain][project["Name"]] = project
				
json_file = open("json_file.json", "w")
json_file.write(json.dumps(domains))
json_file.close()