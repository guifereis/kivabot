import requests
import json
import datetime

import numpy as np

base_url = "https://api.kivaws.org/v1/"

cached_loans = dict()

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

def fetch_newest_loans():
	newest_url = "loans/newest.json"+"?page=1&per_page=10&ids_only=true"

	resp = requests.get(base_url+newest_url)

	new_loan_ids = resp.json()["loans"]

	seen_loan_ids = set()

	new_loan_ids = list(set(new_loan_ids) - seen_loan_ids)


def repayment_url(loan_id):
	return "loans/"+str(loan_id)+"/repayments.json"


def loan_is_direct(loan_id, resp):
	if "code" in resp and resp["code"] == str(4096):
		print("Ignoring loan-id "+str(loan_id)+": "+resp["message"])
		return True
	return False

def process_repayments(loan_id):
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
		assert np.sum(percent_repaid)==1.0
		avg_repayment_days = np.dot(percent_repaid, days_til_repayment_event)
		cached_loans[loan_id] = Loan(loan_id, "partner", reps, days_til_repayment_event, percent_repaid, np.sum(amounts_repaid))
		return avg_repayment_days
	
	repayments = requests.get(base_url+repayment_url(loan_id))
	repayments = repayments.json()
	
	if loan_is_direct(loan_id, repayments):
		# Handle error for invalid loan_id
		# Nonpartner loan, no repayments chart available
		# TODO: Try to fetch data for this case?
		return -1
	
	num_repayment_events = len(repayments)
	if num_repayment_events == 0: # Loan no longer fundraising, abort
		print("Ignoring loan-id "+str(loan_id)+": loan no longer fundraising.")
		return -1
		
	avg_repayment_days = calc_avg_repayment_days(repayments)
	print("AVG REPAYMENT DAYS: "+str(avg_repayment_days))
	return avg_repayment_days
			
	
	
	

fundraising_id = 1430697

funded_id = 1446764

nonpartner_fundraising_id = 1439911



test_loan_id = funded_id

if process_repayments(test_loan_id) >= 0:
	print(cached_loans[test_loan_id])

