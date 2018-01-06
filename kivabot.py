import requests
import json
import datetime
import pickle
from tqdm import tqdm

import numpy as np

base_url = "https://api.kivaws.org/v1/"

cached_loans = dict()
seen_loan_ids = set()

class Loan():
	def __init__(self, loan_id, loan_type, repayment_json=None, days_til_repayment_event=None, percent_repaid=None, loan_total=None):
		self.loan_id = loan_id
		self.loan_type = loan_type
		self.repayment_json = repayment_json
		self.days_til_repayment_event = days_til_repayment_event
		self.percent_repaid = percent_repaid
		self.loan_total = loan_total
	
	def __str__(self):
		# Thanks to: https://pythonadventures.wordpress.com/2011/10/30/using-__str__-print-all-the-attributes-of-an-object/
		sb = []
		for key in self.__dict__:
			sb.append("{key}='{value}'".format(key=key, value=self.__dict__[key]))
	 
		return ', '.join(sb)

def fetch_newest_loans(page=1, per_page=100):
	newest_url = "loans/newest.json"+"?page="+str(page)+"&per_page="+str(per_page)+"&ids_only=true"

	resp = requests.get(base_url+newest_url)
	resp = resp.json()

	new_loan_ids = resp["loans"]
	num_pages = resp["paging"]["pages"]
	
	return set(new_loan_ids), num_pages
	
	# TODO: decide what to do about following 2 lines

	#seen_loan_ids = set()

	#new_loan_ids = list(set(new_loan_ids) - seen_loan_ids)


def repayment_url(loan_id):
	return "loans/"+str(loan_id)+"/repayments.json"


def loan_is_direct(loan_id, resp):
	if "code" in resp and resp["code"] == str(4096):
		#print("Ignoring loan-id "+str(loan_id)+": "+resp["message"])
		return True
	return False

def process_repayments(loan_id):
	# Returns a stringly negative int in case of error. Otherwise,
	# returns "average days to repayment" (see below.)
	def calc_avg_repayment_days(reps):
		# We construct a measure similar to an expected value
		# where days-until-each-repayment is weighted by the
		# percentage of the loan being paid at each repayment.
		# This represents the average time each $ takes to be repaid.
		days_til_repayment_event = np.zeros(len(reps))
		amounts_repaid = np.zeros(len(reps))
		percent_repaid = np.zeros(len(reps))
		
		for rep_idx in range(len(reps)):
			repayment_timestamp = datetime.datetime.fromtimestamp(reps[rep_idx]["period_unixtime"])
			td = repayment_timestamp - datetime.datetime.now()
			days_til_repayment_event[rep_idx] = td.days
			assert days_til_repayment_event[rep_idx] > 0 # will likely be a bug if a loan is repaid the same day I pull it up -- in practice, extremely likely, and not a severe problem.
			amounts_repaid[rep_idx] = reps[rep_idx]["expected_repayment"]
			
		percent_repaid = amounts_repaid/np.sum(amounts_repaid)
		assert np.isclose(np.sum(percent_repaid), 1.0)
		avg_repayment_days = np.dot(percent_repaid, days_til_repayment_event)
		#cached_loans[loan_id] = Loan(loan_id, "partner", reps, days_til_repayment_event, percent_repaid, np.sum(amounts_repaid))
		loan_obj = Loan(loan_id, "partner", reps, days_til_repayment_event, percent_repaid, np.sum(amounts_repaid))
		#seen_loan_ids.add(loan_id)
		return avg_repayment_days, loan_obj
	
	repayments = requests.get(base_url+repayment_url(loan_id))
	repayments = repayments.json()
	
	if loan_is_direct(loan_id, repayments):
		# Handle error for invalid loan_id
		# Nonpartner loan, no repayments chart available
		# TODO: Try to fetch data for this case?
		return -2, repayments
	
	num_repayment_events = len(repayments)
	if num_repayment_events == 0: # Loan no longer fundraising, abort
		#print("Ignoring loan-id "+str(loan_id)+": loan no longer fundraising.")
		return -3, None
		
	avg_repayment_days, loan_obj = calc_avg_repayment_days(repayments)

	return avg_repayment_days, loan_obj

def handle_repayment_processed_return(loan_id, avg_repayment_days, loan_obj, using_tqdm=False, max_days_print_thres=100):
	if avg_repayment_days == -2:
		# We are abusing loan_obj to be the json response in case of error
		print("Ignoring loan-id "+str(loan_id)+": "+loan_obj["message"])
	elif avg_repayment_days == -3:
		print("Ignoring loan-id "+str(loan_id)+": loan no longer fundraising.")
	elif avg_repayment_days < 0:
		print("!!! UNKNOWN ERROR !!!")
	elif avg_repayment_days >= 0:
		if avg_repayment_days < max_days_print_thres:
			msg = ""+str(loan_id)+" AVG REPAYMENT DAYS: "+str(round(avg_repayment_days))
			if using_tqdm:
				tqdm.write(msg)
			else:
				print(msg)
	seen_loan_ids.add(loan_id)
	cached_loans[loan_id] = loan_obj
	

def init_cache(cached_loans_filename=None, seen_loans_filename=None, multithread=False):
	global cached_loans
	global seen_loan_ids
	
	if cached_loans_filename is not None:
		cached_loans = pickle.load( open(cached_loans_filename, "rb" ))
	if seen_loans_filename is not None:
		seen_loan_ids = pickle.load( open(seen_loans_filename, "rb" ))
	
	new_loan_ids, num_newest_pages = fetch_newest_loans(page=1, per_page=500)
	loan_ids = set()
	for cur_page in range(1, num_newest_pages+1)[::-1]:
		new_loan_ids, num_newest_pages = fetch_newest_loans(page=cur_page, per_page=500)
		loan_ids |= new_loan_ids
	print("Num new loan-ids: "+str(len(loan_ids)))
	
	if multithread:
		#t = tqdm(total=len(loan_ids))
		import concurrent.futures
		with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
			future_to_loan_id = {executor.submit(process_repayments, loan_id): loan_id for loan_id in loan_ids}
			for future in tqdm(concurrent.futures.as_completed(future_to_loan_id), total=len(loan_ids)):
				pass # just to update progress bar
			#for future in concurrent.futures.as_completed(future_to_loan_id):
				##tqdm.write(loan_id)
				#t.update() # update progress bar
		for future, loan_id in tqdm(futures.iteritems()):
			#loan_id = future_to_loan_id[future]
			try:
				avg_repayment_days, loan_obj = future.result()
				handle_repayment_processed_return(loan_id, avg_repayment_days, loan_obj, using_tqdm=True)
			except Exception as exc:
				print('%r generated an exception: %s' % (loan_id, exc))
			else:
				print('%r page is %d bytes' % (loan_id, len(data)))
		
	else:
		for loan_id in tqdm(loan_ids):
			avg_repayment_days, loan_obj = process_repayments(loan_id)
			handle_repayment_processed_return(loan_id, avg_repayment_days, loan_obj, using_tqdm=True)
		
	

#fundraising_id = 1430697
#funded_id = 1446764
#nonpartner_fundraising_id = 1439911
#test_loan_id = fundraising_id

#if process_repayments(test_loan_id) >= 0:
	#pass
	#print(cached_loans[test_loan_id])

#for loan_id in fetch_newest_loans():
#	print(loan_id)
#	process_repayments(loan_id)

init_cache(multithread=True)
pickle.dump(cached_loans, open("cached_loans.pickle", "wb"))
pickle.dump(seen_loan_ids, open("seen_loan_ids.pickle", "wb"))

print(".........")
print(cached_loans)
