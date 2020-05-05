import json
from subprocess import getoutput as go

go("mkdir domains")

#Year-Month-Day
date = input("Year-Month-Day")

domains = {}

for domain in go("openstack domain list -f value -c Name").split("\n"):

	go("mkdir domains/%s" % domain)
	domains[domain] = {}
	for project in json.loads(go("openstack  project list --domain %s -f json" % domain)):
		
		go("mkdir domains/%s/%s" % (domain, project["Name"]))		

		volume = json.loads(go("openstack volume list --project %s -f json" % project["Name"]))

		#print("openstack volume list --project %s -f json" % project["Name"])
		
		project["Volume"] =  volume
		project["Instances"] = {}
		projects["Flavors"] = {}
		
		for instance in json.loads(go("openstack server list --project-domain %s --project %s -f json" % (domain, project["Name"]))):
			project["Instances"][instance["ID"]] =  instance
			project["Instances"][instance["ID"]]["Log"]  = go("nova instance-action-list %s" % instance["ID"])
			project["Flavors"][instance["Flavor"]] = json.loads(go("openstack show flavor %s -f json" % instance["Flavor"]))
			#print("nova instance-action-list %s" % instance["ID"])
		
		for deleted_instance in json.loads(go("openstack server list --project-domain %s --project %s --changes-since %s --deleted -f json" % (domain, project["Name"], date))):
			print(deleted_instance)
			project["Instances"][deleted_instance["ID"]] = deleted_instance
			project["Instances"][deleted_instance["ID"]]["Log"] = go("nova instance-action-list %s" % deleted_instance["ID"])
			project["Flavors"][deleted_instance["Flavor"]] = json.loads(go("openstack show flavor %s -f json" % deleted_instance["Flavor"]))

		domains[domain][project["Name"]] = project
				
json_file = open("json_file.json", "w")
json_file.write(json.dumps(domains))
json_file.close()