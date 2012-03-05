import logging
import os
import re

from datetime import datetime
from calendar import timegm

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api.taskqueue import Task

from controllers import facebook
from models.db.user import User
from models.db.favorite import Favorite
from models.db.track import Track
from models.db.counter import Shard
from models.db.station import Station
from models.db.recommendation import Recommendation

from models.api.admin import AdminApi

MEMCACHE_USER_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".user."
MEMCACHE_USER_CONTRIBUTIONS_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".contributions.user."
MEMCACHE_USER_FAVORITES_PREFIX = os.environ["CURRENT_VERSION_ID"] + ".favorites.user."
COUNTER_OF_FAVORITES = "user.favorites.counter."

class UserApi:
	def __init__(self, facebook_id):
		self._facebook_id = str(facebook_id)
		self._memcache_user_id = MEMCACHE_USER_PREFIX + self._facebook_id
		self._memcache_user_contributions_id = MEMCACHE_USER_CONTRIBUTIONS_PREFIX + self._facebook_id
		self._memcache_user_favorites_id = MEMCACHE_USER_FAVORITES_PREFIX + self._facebook_id
		self._counter_of_favorites_id = COUNTER_OF_FAVORITES + self._facebook_id
	
	# Return the user
	@property
	def user(self):
		if not hasattr(self, "_user"):
			self._user = memcache.get(self._memcache_user_id)
			if self._user is None:
				logging.info("User not in memcache")
				self._user = User.get_by_key_name(self._facebook_id)
				if self._user:
					memcache.set(self._memcache_user_id, self._user)
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
			facebook_access_token = facebook_access_token,
			first_name = first_name,
			last_name = last_name,
			email = email,
		)
		user.put()
		logging.info("User put in datastore")
		
		memcache.set(self._memcache_user_id, user)
		logging.info("User put in memcacche")
		
		# Put the user in the proxy
		self._user = user
		
		# Put the user recommendations
		self.task_recommendations()
		
		# Increment admin counter of users
		admin_proxy = AdminApi()
		admin_proxy.increment_users_counter()
		logging.info("Counter of users incremented")
		
		# Mail new user to admins
		self.mail()
		
		return self._user
		
	# Update the facebook user access token
	def update_token(self, facebook_access_token):
		self.user.facebook_access_token = facebook_access_token
		self.user.put()
		logging.info("User access token updated in datastore")
		
		memcache.set(self._memcache_user_id, self.user)
		logging.info("User access token updated in memcache")
	
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
				graph = facebook.GraphAPI(self.user.facebook_access_token)
				accounts = graph.get_connections(self.user.key().name(),"accounts")["data"]
				
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
		
		return self._contributions
	
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

	# Tells if a user is an admin of a specific page 
	def is_admin_of(self, page_id):
		for contribution in self.contributions:
			if(contribution["page_id"] == page_id):
				return True
		return False
	
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
		
	def favorites_query(self, offset):
		q = Favorite.all()
		q.filter("user", self.user.key())
		q.filter("created <", offset)
		q.order("-created")
		favorites = q.fetch(10)
		
		return favorites

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
	
	@property
	def number_of_favorites(self):
		if not hasattr(self, "_number_of_favorites"):
			shard_name = self._counter_of_favorites_id
			self._number_of_favorites = Shard.get_count(shard_name)
		return self._number_of_favorites
	
	def increment_favorites_counter(self):
		shard_name = self._counter_of_favorites_id
		Shard.task(shard_name, "increment")

	def decrement_favorites_counter(self):
		shard_name = self._counter_of_favorites_id
		Shard.task(shard_name, "decrement")
	
	def task_recommendations(self):
		task = Task(
			url = "/taskqueue/recommendations",
			params = {
				"key_name": self._facebook_id,
			}
		)
		task.add(queue_name = "worker-queue")
	
	def save_recommendations(self):
		graph = facebook.GraphAPI(self.user.facebook_access_token)
		items = graph.get_connections("me","links", limit=50)["data"]
				
		recommendations = []
		for item in items:
			if item.has_key("link"):
				m = re.match(r"http://www.youtube.com/watch\?v=([\w_-]+)", item["link"])
				if m is not None:
					recommendations.append(Recommendation(
						youtube_id = m.group(1),
						user = self.user.key(),
					))
				
		db.put(recommendations)
		logging.info("Recommandations put in the datastore")
			
	def recommendations_query(self):
		q = Recommendation.all()
		q.filter("user", self.user.key())
		recommendations = q.fetch(30)
		
		return recommendations
		
		
	
	
		
		
		