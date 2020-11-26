from datetime import datetime, timedelta
from collections import defaultdict
import json

name_to_idx = {
	#indexes of the fields from the sponsors file
	"project" : 0,
	"sponsor" : 13,

	#here are the named indexes of the logs
	"action" : 0, 
	"date" : 4,  
	"first_line" : 0,

	#here are the named indexes of the cpu usage data
	"data" : 0, 
	"instant" : 0,  
	"period_average" : 1
}

#here we have all the relevant state changes to know if the instance is active or inactive so we can check it later
to_on_states = ['create', 'restore', 'start', 'reboot', 'unpause', 'resume', 'unrescue', 'unshelve', 'pause']
to_off_states = ['softDelete', 'forceDelete', 'delete', 'stop', 'shelve', 'suspend', 'error']

empty_value = "-------"
maximum_date = datetime(year = 9999, month = 12, day = 31)

class Processor:
	def __init__(self):
		pass
	
	def process(self, start, end):
		print("starting processor")

		#reading the date
		start_date = datetime.fromisoformat(start)
		end_date = datetime.fromisoformat(end)
		
		#reading the sponsors list
		csv_file = open("templates/full_sponsors.csv", "r")
		with open("templates/full_sponsors.csv") as csv_file:
			project_sponsors = csv_file.read().strip().replace(" ", "").split("\n")[1:-1]

		project_sponsors = defaultdict(lambda: "joabsilva@lsd.ufcg.edu.br", { self._line_to_project(line): self._line_to_sponsor(line) for line in map(self._split_by_comma, project_sponsors) })

		sponsors = {sponsor:{} for sponsor in project_sponsors.values()}
		sponsors["joabsilva@lsd.ufcg.edu.br"] = {} #joab is the sponsor for the support services and he is not in the csv file

		#read the json file
		with open("json_file.json", "r") as json_file:
			data = json.load(json_file)

		abnormal_instances_log = ""
		for domain_name in data:

			domain = data[domain_name]

			for project in domain.values():

				if project["Name"].strip() == "":
					project["Name"] = empty_value

				sponsor = project_sponsors[project["Name"]]

				for abnormal_instance in project["Abnormal_Instances"]:
					abnormal_instances_log += ("%s %s %s %s\n" % (abnormal_instance["Name"], domain_name, project["Name"], sponsor))

				project_mem_usage = 0
				project_vcpu_usage = 0
				project_average_cpu_use = 0
				
				valid_instances = filter(self._is_valid, project["Instances"].values())
				project["Instances"] = sorted(valid_instances, key = self._get_create_date)
				for instance in project["Instances"]:
					
					instance_log = self._extract_actions(instance["Log"])
					instance_time_use = self._total_time(instance_log)
					
					instance_mem_usage = self._get_instance_memory(project, instance) * instance_time_use.total_seconds()
					project_mem_usage += instance_mem_usage
					instance_vcpu_usage = self._get_instance_vcpus(project, instance) * instance_time_use.total_seconds()
					project_vcpu_usage += instance_vcpu_usage
					instance_average_cpu_use = self._usage_cpu_average(instance["Cpu_Usage_List"])
					project_average_cpu_use += instance_average_cpu_use * instance_vcpu_usage
					status = self._get_status(instance_log)

					instance["Create_Date"] = self._date_br_format(get_create_date(instance).date())
					instance["Time_Use"] = self._days_hours_minutes(instance_time_use)
					instance["Status"] = status
					instance["Usage_Cpu_Average"] = instance_average_cpu_use

					if instance["Name"].strip() == "":
						instance["Name"] = empty_value

				project["Total_Mem_Usage"] = project_mem_usage
				project["Total_Vcpu_Usage"] = project_vcpu_usage 
				project["Usage_Cpu_Average"] = project_average_cpu_use / max(project_vcpu_usage, 1)
				
				project["Domain"] = domain_name
				
				sponsors[sponsor][project["Name"]] = project
				sponsors[sponsor][project["Name"]]["Domain"] = domain_name

		with open("processed_data.json", "w") as json_file:
			json_file.write(json.dumps(sponsors))

		with open("log.txt", "w") as log_abnormal_instances:
			log_abnormal_instances.write(json.dumps(abnormal_instances_log))
	
	def _line_to_project(self, line):
		return line[name_to_idx['project']]

	def _line_to_sponsor(self, line):
		return line[name_to_idx['sponsor']]

	def _split_by_comma(self, line):
		return line.split(',')

		#this function is to get the instance create date
	def _get_create_date(self, instance):
		return datetime.fromisoformat(_extract_actions(instance["Log"])[name_to_idx['first_line']][name_to_idx['date']])

	#this function is to format the usage time for output  
	def _days_hours_minutes(self, total):
		days = total.days
		hours = int(total.seconds/3600)
		minutes = int(total.seconds/60)%60
		return  "%s Dias, %s Horas e %s Minutos" % (days, hours, minutes)

	#this function is to extract actions from the instance's logs that are in the nova cli output format
	def _extract_actions(self, log):
		
		#here the result  indices are [Action, Request_ID, Message, Start_Time, Update_Time]
		return [line.replace('|', " ").split() for line in log.split("\n")[3:-1]]

	#this function is to format the date for output
	def _date_br_format(self, date):
		return "%02d-%02d-%d" % (date.day, date.month, date.year)

	#this function is to get the last status of an instance
	def _get_status(self, log_list):
		status = "Ativa"
		for line in log_list:
			if datetime.fromisoformat(line[name_to_idx['date']]) > end_date:
				break
			
			if line[name_to_idx['action']] == 'pause':
				status = "Ativa(Pausada)"

			elif line[name_to_idx['action']] in to_on_states:
				status = "Ativa"
			
			elif line[name_to_idx['action']] in to_off_states:
				status = "Inativa"

		return status

	#this function is to calculate the total time of instance use
	def _total_time(self, log_list):

		#first we need an accumulator
		total = timedelta(days = 0)
		
		'''
		the algorithm here is to go through all the actions taken by the instance and always look back
		to see if we need to increase the time of using the instance, if the instance was created 
		before the initial consultation date and is turned on when the initial date is exceeded, we will
		also need to increase the time from this date until the first action taken within the consulted
		time interval or until the end date of the consultation
		'''
		on = False
		last = start_date

		for line in log_list:
			date = datetime.fromisoformat(line[name_to_idx['date']])
			
			if date > end_date:
				break

			if date > start_date:
				if on:
					total += date - last
				last = date

			if line[name_to_idx['action']] in to_on_states:
				on = True
			elif line[name_to_idx['action']] in to_off_states:
				on = False
		if on:
			total += end_date - last
		return total

	def _is_not_empty(self, instance):
		return self._extract_actions(instance["Log"]) != []

	def _is_valid(self, instance):
		return self._is_not_empty(instance) and self._get_create_date(instance) < end_date

	def _get_instance_memory(self, project ,instance):
		return int(project["Flavors"][instance["Flavor"]]["ram"]) // 1024

	def _get_instance_vcpus(self, project ,instance):
		return int(project["Flavors"][instance["Flavor"]]["vcpus"])

	def _usage_cpu_average(cpu_usage_list):
		print(len(cpu_usage_list))
		total_cpu_usage = 0
		number_of_instantes = 0
		if(len(cpu_usage_list) == 0):
			return 0
		for period_average in cpu_usage_list[name_to_idx["data"]]["statistics"]:
			total_cpu_usage += period_average[name_to_idx["period_average"]]
			number_of_instantes += 1
		
		average_cpu = total_cpu_usage / number_of_instantes
		return average_cpu
