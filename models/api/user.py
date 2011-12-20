import logging
import os

from google.appengine.ext import db
from google.appengine.api import memcache

from controllers import facebook
from models.db.user import User

MEMCACHE_USER_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".user."
MEMCACHE_USER_CONTRIBUTIONS_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".contributions.user."

class UserApi:
	def __init__(self, facebook_id):
		self._facebook_id = str(facebook_id)
		self._memcache_facebook_id = MEMCACHE_USER_PREFIX + self._facebook_id
		self._memcache_user_contributions_id = MEMCACHE_USER_CONTRIBUTIONS_PREFIX + self._facebook_id
	
	# Return the user
	@property
	def user(self):
		if not hasattr(self, "_user"):
			self._user = memcache.get(self._memcache_facebook_id)
			if self._user is None:
				logging.info("User not in memcache")
				self._user = User.get_by_key_name(self._facebook_id)
				if self._user:
					logging.info("User exists")
					memcache.set(self._memcache_facebook_id, self._user)
					logging.info("%s %s put in memcache"%(self._user.first_name, self._user.last_name))
				else:
					logging.info("User does not exist")
			else:
				logging.info("%s %s already in memcache"%(self._user.first_name, self._user.last_name))
		return self._user
	
	# Put the user
	def put_user(self, facebook_id, facebook_access_token, first_name, last_name, email):
		user = User(
			key_name = str(facebook_id),
			facebook_access_token = str(facebook_access_token),
			first_name = str(first_name),
			last_name = str(last_name),
			email = str(email),
		)
		user.put()
		logging.info("User put in datastore")
		
		memcache.set(self._memcache_facebook_id, user)
		logging.info("User put in memcacche")
		
		# Put the user in the proxy
		self._user = user
		
		return self._user
	
	# Update the facebook user access token
	def update_token(self, facebook_access_token):
		self.user.facebook_access_token = facebook_access_token
		self.user.put()
		logging.info("User access token updated in datastore")
		
		memcache.set(self._memcache_facebook_id, self.user)
		logging.info("User access token updated in memcache")
		
	# Return the user contributions (pages he's admin of)
	@property
	def contributions(self):
		if not hasattr(self, "_contributions"):
			self._contributions = memcache.get(self._memcache_user_contributions_id)
			
			if self._contributions is None:
				graph = facebook.GraphAPI(self.user.facebook_access_token)
				accounts = graph.get_connections(self.user.key().name(),"accounts")["data"]
				
				contributions = []
				if isinstance(accounts, list):
					for account in accounts:
						if(account["category"] != "Application"):
							contribution = {
								"page_name": account["name"],
								"page_access_token": account["access_token"],
								"page_id": account["id"],
							}
							contributions.append(contribution)
		
				self._contributions = contributions
				memcache.set(self._memcache_user_contributions_id, self._contributions)
				logging.info("User contributions put in memcache")
			else:
				logging.info("User contributions already in memcache")
		
		return self._contributions
	
	# Tells if a user is an admin of a specific page 
	def is_admin_of(self, page_id):
		for contribution in self.contributions:
			if(contribution["page_id"] == page_id):
				return True
		return False
		
	# Retrieves the page contribution for a given page and user (access token, page name)
	def get_page_contribution(self, page_id):
		page_contribution = None
		for contribution in self.contributions:
			if(contribution["page_id"] == page_id):
				page_contribution = contribution
				break
		return page_contribution
	
	

		
		
		
		
		