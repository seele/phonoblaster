/*-------- SHUFFLE CONTROLLER --------*/

function ShuffleController(tracklistManager){
	this.tracklistManager = tracklistManager;
	this.init();
}

ShuffleController.prototype = {
	
	//Listen to clicks on shuffle button
	init: function(){
		var that = this;
		$("a#shuffle").click(function(){
			nb_of_tracks = that.tracklistManager.tracklist.length
			if(nb_of_tracks == 9){
				//Display during a small intervall a "list full button"
				that.shuffleNotPossible();
			}
			else{
				$(this).hide();
				$("#shuffle").append(
					$("<img/>")
						.attr("src","/static/images/small-ajax-loader.gif")
						.addClass("loader")
				);
				that.shuffle();
			}
			return false;
		});
	},
	
	shuffle: function(){
		var that = this;
		$.ajax({
			url: "/station/shuffle",
			type: "POST",
			dataType: "json",
			timeout: 60000,
			data: {
				station_key: station_key,
			},
			error: function(xhr, status, error) {
				console.log('An error occurred: ' + error + '\nPlease retry.');
			},
			success: function(json){
				if(json.status == "shuffled"){						
					console.log("Your shuffle operation has been completed");
					that.shuffleCompleted();
				}
				else{
					console.log("Tracklist full");
					that.shuffleUncompleted();
				}
			},
		});
		
		
	},
	
	shuffleCompleted: function(){
		$("#shuffle img.loader").remove()
		$("a#shuffle")
			.attr("id","just_shuffled")
			.html("Just shuffled!")
			.show()
			
		setTimeout(function(){
			$("a#just_shuffled")
				.attr("id","shuffle")
				.html("Shuffle now!")
		},1000)
	},
	
	shuffleUncompleted: function(){
		$("#shuffle img.loader").remove()
		$("a#shuffle")
			.attr("id","not_shuffled")
			.html("Tracklist full!")
			.show()
			
		setTimeout(function(){
			$("a#not_shuffled")
				.attr("id","shuffle")
				.html("Shuffle now!")
		},1000)
	},	
	
	shuffleNotPossible: function(){
		$("a#shuffle")
			.attr("id","not_shuffled")
			.html("Tracklist full!")
			
		setTimeout(function(){
			$("a#not_shuffled")
				.attr("id","shuffle")
				.html("Shuffle now!")
		},1000)
	},
	
}