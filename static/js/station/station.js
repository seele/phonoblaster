function StationClient(user, admin, station){
	this.user = user;
	this.admin = admin;
	this.station = station;
	this.channel_id = null;
	this.presence_manager = null;
	this.comment_manager = null;
	this.status_manager = null;
	this.search_manager = null;
	this.queue_manager = null;
	this.presence();
}

StationClient.prototype = {
	
	// Add a new presence: request Client ID and Token from Google App Engine
	presence: function(){
		var that = this;
				
		$.ajax({
			url: "/api/presences",
			type: "POST",
			dataType: "json",
			timeout: 60000,
			data: {
				shortname: that.station.shortname,
			},
			error: function(xhr, status, error) {
				PHB.log('An error occurred: ' + error + '\nPlease retry.');
			},
			success: function(json){				
				// Store the presence channel id
				that.channel_id = json.channel_id;
				
				// Create a presence channel
				var channel = new goog.appengine.Channel(json.channel_token);
				
				// Open connection and hook callbacks
				var socket = channel.open();
				socket.onerror = window.location.reload;
				socket.onclose = window.location.reload;
				
				// Subscribe to the station channel
				var station_client = that;
				socket.onopen = function(){
					station_client.pubnub();
				}
				
				// We do not hook the following callback
				// - socket.onmessage
			},
		});
	},
	
	// Subscribe to the station channel with Pubnub
	pubnub: function(){
		var that = this;
		var pubnub_channel = PHB.version + "-" + this.station.shortname
		// Subscribe to the station channel with Pubnub
		PUBNUB.subscribe({
	        channel: pubnub_channel,      
	        error: function(){
				alert("Connection Lost. Will auto-reconnect when Online.");
			},
	        callback: function(message) {
	            that.dispatch(message);
	        },
	        connect: function(){
				// Fetch all the content: presences, comments, queue
				that.fetch();
	        }
		})
	},
	
	// Fetch presences, comments and queue after connection to pubnub
	fetch: function(){
		this.presence_manager = new PresenceManager(this);
		this.comment_manager = new CommentManager(this);
		this.status_manager = new StatusManager(this);
		this.search_manager = new SearchManager(this);
		this.queue_manager = new QueueManager(this);
	},
	
	// Dispatch incoming messages according to their content
	dispatch: function(data){
		var message = JSON.parse(data);
		var event = message.event;
		var content = message.content;
		
		if(event == "new-presence"){
			PHB.log("new-presence");
			this.presence_manager.add(content);
		}
		if(event == "presence-removed"){
			PHB.log("presence-removed");
			this.presence_manager.remove(content);
		}
		if(event == "new-comment"){
			PHB.log("new-comment");
			this.comment_manager.add(content);
		}
	},
	
}
