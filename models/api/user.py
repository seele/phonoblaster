import logging
import os
import re

from datetime import datetime
from datetime import timedelta
from calendar import timegm

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api.taskqueue import Task

from controllers import facebook
from controllers import config

from models.db.user import User
from models.db.favorite import Favorite
from models.db.track import Track
from models.db.counter import Shard
from models.db.station import Station

from controllers.facebook import GraphAPIError

from models.api.admin import AdminApi

MEMCACHE_USER_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".user."
MEMCACHE_USER_CONTRIBUTIONS_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".contributions.user."
MEMCACHE_USER_NON_CREATED_PROFILES_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".non.created.profiles.user."
MEMCACHE_USER_PROFILES_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".profiles.user."
MEMCACHE_USER_PROFILE_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".profile.user."
MEMCACHE_USER_FAVORITES_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".favorites.user." # TO BE MOVED TO stationapi
COUNTER_OF_FAVORITES = "user.favorites.counter."

class UserApi:
	def __init__(self, uid, code = None):
		self._uid = uid
		self._code = code # only for an authenticated user
		self._memcache_user_id = MEMCACHE_USER_PREFIX + self._uid
		self._memcache_user_contributions_id = MEMCACHE_USER_CONTRIBUTIONS_PREFIX + self._uid
		self._memcache_user_non_created_profiles_id = MEMCACHE_USER_NON_CREATED_PROFILES_PREFIX + self._uid
		self._memcache_user_profiles_id = MEMCACHE_USER_PROFILES_PREFIX + self._uid
		self._memcache_user_profile_id = MEMCACHE_USER_PROFILE_PREFIX + self._uid
		self._memcache_user_favorites_id = MEMCACHE_USER_FAVORITES_PREFIX + self._uid
		self._counter_of_favorites_id = COUNTER_OF_FAVORITES + self._uid
	
	# Return the user 
	@property
	def user(self):
		if not hasattr(self, "_user"):
			self._user = memcache.get(self._memcache_user_id)
			if self._user is None:
				logging.info("User not in memcache")
				self._user = User.get_by_key_name(self._uid)
				if self._user:
					memcache.set(self._memcache_user_id, self._user)
					logging.info("%s %s put in memcache"%(self._user.first_name, self._user.last_name))
				else:
					logging.info("User does not exist")
			else:
				logging.info("%s %s already in memcache"%(self._user.first_name, self._user.last_name))
		return self._user	
	
	# Returns the user access token (facebook)
	@property
	def access_token(self):
		if not hasattr(self, "_access_token"):
			self._access_token = None
			if self._code:
				token_response = facebook.get_access_token_from_code(self._code, config.FACEBOOK_APP_ID, config.FACEBOOK_APP_SECRET)
				
				if "access_token" in token_response:
					self._access_token = token_response["access_token"][-1]
		
		return self._access_token
	
	# Puts new user in the datastore	
	def put_user(self, uid, first_name, last_name, email):
		user = User(
			key_name = uid,
			first_name = first_name,
			last_name = last_name,
			email = email,
		)
		user.put()
		logging.info("User put in datastore")

		#Adding contributions to user
		graph = facebook.GraphAPI(self.access_token)
		try:
			accounts = graph.get_connections(user.key().name(),"accounts")["data"]
		except GraphAPIError:
			logging.info("User did not accept that Phonoblaster can manage his pages.")
			accounts = []
			
		contributions = []
		if isinstance(accounts, list):
			for account in accounts:
				if(account["category"] != "Application"):
					contribution = {
						"page_name": account["name"],
						"page_id": account["id"],
					}
					contributions.append(contribution)

		# Put the user in the proxy
		self._user = user

		#Creating and storing the keys pointing to stations entities, even when a page is not associated with a phonoblaster station
		logging.info('Proceeding to stations field creation for user %s %s.'%(first_name, last_name))
		self.set_stations_field(contributions)
		
		# Increment admin counter of users
		admin_proxy = AdminApi()
		admin_proxy.increment_users_counter()
		logging.info("Counter of users incremented")
		
		# Mail new user to admins
		self.mail()
		
		return self._user
	
	def mail(self):
		admin_proxy = AdminApi()
		
		subject = "New phonoblaster user: %s %s" % (self.user.first_name, self.user.last_name)
		body = """
A new user has logged into Phonoblaster:
%s %s, %s
		
Global number of users: %s
		""" %(self.user.first_name, self.user.last_name, self.user.email, admin_proxy.number_of_users)
		
		task = Task(
			url = "/taskqueue/mail",
			params = {
				"to": "activity@phonoblaster.com",
				"subject": subject,
				"body": body,
			}
		)
		task.add(queue_name = "worker-queue")

	
	# Return the user contributions (pages he's admin of)
	@property
	def contributions(self):
		if not hasattr(self, "_contributions"):
			self._contributions = memcache.get(self._memcache_user_contributions_id)
			
			if self._contributions is None:
				graph = facebook.GraphAPI(self.access_token)
				try:
					accounts = graph.get_connections(self.user.key().name(),"accounts")["data"]
				except GraphAPIError:
					logging.info("User did not accept that Phonoblaster can manage his pages.")
					accounts = []
					
				contributions = []
				if isinstance(accounts, list):
					for account in accounts:
						if(account["category"] != "Application"):
							contribution = {
								"page_name": account["name"],
								"page_id": account["id"],
							}
							contributions.append(contribution)
		
				self._contributions = contributions

				memcache.set(self._memcache_user_contributions_id, self._contributions)
				logging.info("User contributions put in memcache")
			else:
				logging.info("User contributions already in memcache")


			# Updating stations fileds
			doStationUpdate = False # boolean that will let the system know if it has to perform an update
			if(self.user.stations):
				logging.info('Time since last stations field update for user %s %s (in hours) : %s'% (self.user.first_name, self.user.last_name, str((timegm(datetime.utcnow().utctimetuple()) - timegm(self.user.updated.utctimetuple()))/3600)))

				if(self.user.updated < datetime.utcnow() - timedelta(1,0)):
					logging.info('Last update more than 24h ago, will proceed to user stations field update.')
					doStationUpdate = True
				else:
					logging.info('Last update less than 24h ago, user stations field update not needed.')
					doStationUpdate = False
			else:
				logging.info('No stations were found for user %s %s, will proceed to station fields creation.'%(self.user.first_name, self.user.last_name))
				doStationUpdate = True

			# Performing update or not depending on doStationUpdate
			if( doStationUpdate ):
				if(not self.user.stations):
					self.user.stations = []

				# Performing update
				self.set_stations_field(self._contributions)

				

		return self._contributions

	def set_stations_field(self, contributions):
		# Creating and storing the keys pointing to stations entities, even when a page is not associated with a phonoblaster station
		keys = [db.Key.from_path('Station', c["page_id"]) for c in contributions]
		self.user.stations = keys
		self.user.put()
		logging.info("Stations field updated in datastore")
		memcache.set(self._memcache_user_id, self.user) #keeping the memcache up to date
		logging.info("Stations field updated in memcache")

	
	def reset_contributions(self):
		memcache.delete(self._memcache_user_contributions_id)
	
	# Return the user stations (stations created he's admin of)
	@property
	def stations(self):
		if not hasattr(self, "_stations"):
			contributions = self.contributions
			page_ids = [c["page_id"] for c in contributions]
			
			results = Station.get_by_key_name(page_ids)
			stations = []
			
			for result in results:
				if result is not None:
					stations.append(result)
					
			self._stations = stations
		
		return self._stations

	# TO BE CHANGED : improvements possible without accessing facebook
	# Tells if a user is an admin of a specific page 
	def is_admin_of(self, page_id):
		for contribution in self.contributions:
			if(contribution["page_id"] == page_id):
				return True
		return False
	
	# TO BE CHANGED : get_favorites is now for a station not a user
	def get_favorites(self, offset):
		timestamp = timegm(offset.utctimetuple())
		memcache_favorites_id = self._memcache_user_favorites_id + "." + str(timestamp)
		
		past_favorites = memcache.get(memcache_favorites_id)
		if past_favorites is None:
			logging.info("Past favorites not in memcache")
			
			favorites = self.favorites_query(offset)
			logging.info("Past favorites retrieved from datastore")
			
			extended_favorites = Favorite.get_extended_favorites(favorites)
			past_favorites = extended_favorites
			
			memcache.set(memcache_favorites_id, past_favorites)
			logging.info("Extended favorites put in memcache")
		else:
			logging.info("Favorites already in memcache")
		
		return past_favorites
	
	# TO BE CHANGED : move to stationapi
	def favorites_query(self, offset):
		q = Favorite.all()
		q.filter("user", self.user.key())
		q.filter("created <", offset)
		q.order("-created")
		favorites = q.fetch(10)
		
		return favorites

	# TO BE CHANGED : move to stationapi
	def add_to_favorites(self, track):
		# Check if the favorite hasn't been stored yet
		q = Favorite.all()
		q.filter("user", self.user.key())
		q.filter("track", track.key())
		existing_favorite = q.get()
		
		if(existing_favorite):
			logging.info("Track already favorited by this user")
		else:			
			favorite = Favorite(
				track = track.key(),
				user = self.user.key(),
			)
			favorite.put()
			logging.info("Favorite saved into datastore")
	
			self.increment_favorites_counter()
			logging.info("User favorites counter incremented")
			
			Track.increment_favorites_counter(track.key().id())
			logging.info("Track favorites counter incremented")
		
	# TO BE CHANGED : move to stationapi
	def delete_from_favorites(self, track):
		q = Favorite.all()
		q.filter("user", self.user.key())
		q.filter("track", track.key()) 
		favorite = q.get()
				
		if favorite is None:
			logging.info("This track has never been favorited by this user")
		else:
			favorite.delete()
			logging.info("Favorite deleted from datastore")
			
			self.decrement_favorites_counter()
			logging.info("User Favorites counter decremented")
			
			Track.decrement_favorites_counter(track.key().id())
			logging.info("Track favorites counter decremented")
	
	# TO BE CHANGED : move to stationapi
	@property
	def number_of_favorites(self):
		if not hasattr(self, "_number_of_favorites"):
			shard_name = self._counter_of_favorites_id
			self._number_of_favorites = Shard.get_count(shard_name)
		return self._number_of_favorites
	
	# TO BE CHANGED : move to stationapi
	def increment_favorites_counter(self):
		shard_name = self._counter_of_favorites_id
		Shard.task(shard_name, "increment")

	# TO BE CHANGED : move to stationapi
	def decrement_favorites_counter(self):
		shard_name = self._counter_of_favorites_id
		Shard.task(shard_name, "decrement")

################################################################################################################################################
##											PROFILE ITERATION
################################################################################################################################################
	@property
	def profile(self):
		if not hasattr(self, "_profile"):
			self._profile = memcache.get(self._memcache_user_profile_id)
			if self._profile is None:
				logging.info("User Profile not in memcache")
				user = self.user
				if user is not None:
					profile_ref = self.user.profile
					if profile_ref is not None:
						station = User.station.get_value_for_datastore(profile_ref)
						if station:
							self._profile = {
								"key_name": station.key().name(),
								"shortname": station.shortname,
								"name": station.name,
								"type": station.type,
							}
							memcache.set(self._memcache_user_profile_id, self._profile)
							logging.info("%s %s's profile put in memcache"%(user.first_name, user.last_name))
						else:
							logging.error("Profile reffers to a non existing station!")
					else:
						logging.info("User has no profile yet.")
				else:
					logging.info("User does not exist")
			else:
				logging.info("%s %s's profile already in memcache"%(self.user.first_name, self.user.last_name))
		return self._profile	

	@property
	def profiles(self):
		if not hasattr(self, "_profiles"):
			self._profiles = memcache.get(self._memcache_user_profiles_id)
			if self._profiles is None:
				self._profiles = []
				stations = self.stations
				for i in xrange(0,len(stations)):
					station = stations[i]
					self._profiles.append(
						{
							"key_name":s.key().name(),
							"name": s.name, 
							"shortname": s.shortname,
							"type": s.type
						})
				memcache.set(self._memcache_user_profiles_id, self._profiles)
				logging.info("%s %s's profiles put in memcache"%(self.user.first_name, self.user.last_name))
			else:
				logging.info("%s %s's profiles already in memcache"%(self.user.first_name, self.user.last_name))
		return self._profiles

	@property
	def non_created_profiles(self):
		if not hasattr(self, "_non_created_profiles"):
			self._non_created_profiles = memcache.get(self._memcache_user_non_created_profiles_id)
			if self._non_created_profiles is None:
				self._non_created_profiles = []

				# Pages
				contributions = self.contributions
				profiles = self.profiles
				for i in xrange(0,len(contributions)):
					# If contribution page_id not in profiles add it to the list of non created profiles
					contribution = contributions[i]
					is_created = False
					for j in xrange(0,len(profiles)):
						profile = profiles[j]
						if contribution["page_id"] == profile["key_name"]:
							# Profile associated to facebook fan page already creted
							is_created = True
							break

					if not is_created:
						# Profile associated to fan page non existing, adding it to the list
						self._non_created_profiles.append(
							{
								"key_name": contribution["page_id"],
								"name": contribution["page_name"],
								"type": "page"
							})

				# Profile
				is_created = False
				for j in xrange(0,len(profiles)):
					profile = profiles[j]
					if self.user.key().name()  == profile["key_name"]:
						# Profile associated to user already creted
						is_created = True
						break

				if not is_created:
					self._non_created_profiles.append(
						{
							"key_name": self.user.key().name(),
							"name": self.user.first_name+" "+self.user.last_name,
							"type": "user"
						})

				memcache.set(self._memcache_user_non_created_profiles_id, self._non_created_profiles)
				logging.info("%s %s's non created profiles put in memcache"%(self.user.first_name, self.user.last_name))

			else:
				logging.info("%s %s's non created profiles already in memcache"%(self.user.first_name, self.user.last_name))

		return self._non_created_profiles

	def set_profile(self, key_name):
		# We first need to check if key_name is in the profiles of the user
		is_in_profiles = False
		for i in xrange(0,len(self.profiles)):
			if key_name == self.profiles[i]["key_name"]:
				is_in_profiles = True
				break

		if is_in_profiles:
			# Retrieving the associated station
			station = Station.get_by_key_name(key_name)
			logging.info("Station retrieved from datastore")

			user = self.user

			user.profile = station.key()
			user.put()
			logging.info("User put in datastore")
			memcache.set(self._memcache_user_id, self.user)
			logging.info("User put in memcache")
			self._user = user


