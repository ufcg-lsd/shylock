from datetime import datetime, timedelta
from subprocess import getoutput as go

atual = datetime.now()

def run(script_file, parameters):
	
	return go("./%s %s" % (script_file, parameters))
	


def main():
	
	last_date = datetime.now()

	while True:
		atual = datetime.now()

		if last_date.month != atual.month:
			
			#scripts_parameters
			start_date = "%d-%.2d-01" % (last_date.year, last_date.month)
			end_date = "%d-%.2d-01" % (atual.year, atual.month)
			exibition_date = "%.2d/%d" % (last_date.month, last_date.year)
			interval_date = "--start_date %s --end_date %s" % (start_date, end_date)

			response_data = run("get_data.py", interval_date)
			print(response_data)

			response_process = run("process_data.py", interval_date)
			print(response_process)

			#generate_reports...
			pass

			
			

		else:
			last_date = atual

		#sleep()




if __name__ == "__main__":
	main()

