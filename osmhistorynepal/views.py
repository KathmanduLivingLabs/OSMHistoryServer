from django.shortcuts import render

import sys
import json
from django.http import JsonResponse
from django_hstore import hstore
from django_hstore.hstore import DictionaryField
from django.contrib.gis.geos import Point
from osmhistorynepal.models import Member, Feature # your appname.models, and your model names, here
from django.db.models import Count
from django.contrib.gis.geos import Polygon
from datetime import datetime
from django.db import connection

# define the response obj
def nepal_statistics_view(request):
	# get all the objects
	ob = Feature.geoobjects
	# make our json obj
	nstat = {}
	# count the distinct mappers
	nstat['mappers'] = ob.all().values('uid').distinct().count()
	# count the distinct buildings
	nstat['buildings'] = ob.filter(tags__values__contains=['building']).values( \
		"feature_type","feature_id").distinct().count()
	# count the distinct roads
	nstat['roads'] = ob.filter(Q(tags__contains={'bridge':'yes'}) | Q(tags__contains={'tunnel':'yes'}) | \
        	Q(tags__values__contains=['highway']) | Q(tags__values__contains=['tracktype']) \
		).values("feature_type","feature_id").distinct().count()
	# count the distinct schools
	nstat['schools'] = ob.filter(Q(tags__values__contains=['school']) | Q(tags__values__contains=['college']) | \
        	Q(tags__values__contains=['university']) | Q(tags__values__contains=['kindergarten']) | \
		Q(tags__values__contains=['music_school'])).values("feature_type","feature_id").distinct().count()
	# count the distinct hospitals
	nstat['hospitals'] = ob.filter(Q(tags__values__contains=['hospital']) \
        	).values("feature_type","feature_id").distinct().count()
	# wrap it up in a json format and return it
	return JsonResponse(nstat)
    
# define the response obj
# request = start, end, mn_x, mn_y, mx_x, mx_y, user
# obviously this is still fundamentally broken
# since i have not yet gone to the trouble of extracting the above values
# from "request"
def selection_statistics_view(request, range, mn_x, mn_y, mx_x, mx_y, user):
	# parse range
	sstart,send = range.split(",") # 2007-08-29T04:08:07+05:45,2007-08-29T04:08:07+05:45
	start = datetime.strptime(sstart, '%Y-%m-$dT%h:%M:%s%z')
	end = datetime.strptime(send, '%Y-%m-$dT%h:%M:%s%z')
	# define our bounding box
	box = Polygon.from_bbox((mn_x, mn_y, mx_x, mx_y))
	# get all the objects
	ndtmp = Feature.geoobjects.filter(Q(point__contained=box) & Q(feature_type='node'))
	# get the unique ids from ndtmp as strings
	strids = ndtmp.extra({'feature_id_str':"CAST(feature_id AS VARCHAR)"}).order_by( \
		'-feature_id_str').values_list('feature_id_str',flat=True).distinct()
	# find all members whose ref values can be found in stride
	okmems = Member.objects.filter(ref__in=strids)
	# find all features containing one or more members in the accepted members list
	relsways = Feature.geoobjects.filter(members__in=okmems)
	# combine that with my existing list of allowed member-less features
	ob = relsways | ndtmp
	# for more, see: http://stackoverflow.com/questions/40585055/querying-objects-using-attribute-of-member-of-many-to-many/40602515#40602515
	# make our json obj
	stat = {}
	# selection statistics card
	sstat = {}
	# count the distinct buildings as of the start time
	bl = ob.filter(tags__values__contains=['building'])
	sstat['Buildings_start'] = bl.filter(timestamp__lte=start).values("feature_type","feature_id").distinct().count()
	# count the distinct buildings as of the end time
	sstat['Buildings_end'] = bl.filter(timestamp__lte=end).values("feature_type","feature_id").distinct().count()
	# count the distinct roads as of the start time
	rd = ob.filter(Q(tags__contains={'bridge':'yes'}) | Q(tags__contains={'tunnel':'yes'}) | \
        	Q(tags__values__contains=['highway']) | Q(tags__keys__contains=['tracktype']) )
	sstat['Roads_start'] = rd.filter(timestamp__lte=start).values("feature_type","feature_id").distinct().count()
	# count the distinct roads as of the end time
	sstat['Roads_end'] = rd.filter(timestamp__lte=end).values("feature_type","feature_id").distinct().count()
	# count the distinct schools as of the start time
	sc = ob.filter(Q(tags__values__contains=['school']) | Q(tags__values__contains=['college']) | \
        	Q(tags__values__contains=['university']) | Q(tags__values__contains=['kindergarten']) | \
		Q(tags__values__contains=['music_school']))
	# count the distinct schools as of the end time
	sstat['Schools_end'] = sc.filter(timestamp__lte=end).values("feature_type","feature_id").distinct().count()
	sstat['Schools_end'] = sc.filter(timestamp__lte=end).values("feature_type","feature_id").distinct().count()
	# count the distinct hospitals as of the start time
	hs = ob.filter(tags__values__contains=['hospital'])
	sstat['Hospitals_start'] = hs.filter(timestamp__lte=start).values("feature_type","feature_id").distinct().count()
	sstat['Hospitals_end'] = hs.filter(timestamp__lte=end).values("feature_type","feature_id").distinct().count() 
	# wrap it into the greater structure
	stat['Selection Statistics'] = sstat
	# leaderboards
	# ways
	ws = ob.filter(Q(timestamp__range=[start,end]) & Q(feature_type='way')).values_list('user').annotate( \
        	num=Count('user')).order_by('-num')
	war = [ [ ("OSM Username",ws[0][0]), ("Ways",ws[0][1]), ("Rank","first") ] \
        	[ ("OSM Username",ws[1][0]), ("Ways", ws[1][1]), ("Rank","second") ] \
		[ ("OSM Username", ws[2][0]), ("Ways", ws[1][1]), ("Rank","third")] ]
	# nodes
	ns = ob.filter(Q(timestamp__range=[start,end]) & Q(feature_type='node')).values_list('user').annotate( \
        	num=Count('user')).order_by('-num')
	nar = [ [ ("OSM Username", ns[0][0]), ("Nodes", ns[0][1]), ("Rank", "first") ] \
        	[ ("OSM Username", ns[1][0]), ("Nodes", ns[1][1]), ("Rank", "second") ] \
		[ ("OSM Username", ns[2][0]), ("Noses", ns[1][1]), ("Rank", "third")] ]
	# put them in our stat object and find most freq. edited POI
	foundnodes = False
	foundways = False
	pres = [ "first", "second", "third" ]
	for index in range(len(pres)):
        	# Nodes
		stat['Nodes'][pres[index]] = nar[index]
		stat['Nodes'][pres[index]]['Most Frequently Edited POI'] = ob.filter(Q(user=nar[index][0][1]) & \
			Q(timestamp__range=[start,end]) & Q(feature_type='node')).raw('''SELECT k, v, count(*) \
			as count FROM ( SELECT skeys(tags) AS k, svals(tags) \
			as v, user, timestamp FROM populate_feature) AS t \
			WHERE k='amenity' GROUP BY k, v ORDER BY count DESC LIMIT 1''')
		# http://stackoverflow.com/questions/12522966/django-orm-hstore-counting-unique-values-of-a-key
		if user == stat['Nodes'][pres[index]]['OSM Username']:
			stat['Nodes'][pres[index]]['highlighted'] = True
			foundnodes = True
		# Ways
		stat['Ways'][pres[index]] = war[index]
		stat['Ways'][pres[index]]['Most Frequently Edited POI'] = ob.filter(Q(user=nar[index][0][1]) & \
			Q(timestamp__range=[start,end]) & Q(feature_type='way')).raw('''SELECT k, v, count(*) \
			as count FROM ( SELECT skeys(tags) AS k, svals(tags) \
			as v, user, timestamp FROM populate_feature) AS t \
			WHERE k='amenity' GROUP BY k, v ORDER BY count DESC LIMIT 1''')
		if user == stat['Ways'][pres[index]]['OSM Username']:
			stat['Ways'][pres[index]]['highlighted'] = True
			foundways = True
	# user search nodes
	if user != None and not foundnodes:
        	stat['Nodes']['user']['OSM Username'] = user
		foundnr = False
		for index, item in enumerate(ns):
			if item[index][0] == user:
				stat['Nodes']['user']['rank'] = index 
				break
		if not foundnr:
			stat['Nodes']['user']['rank'] = 0			
		stat['Nodes']['user']['highlighted'] = True
		stat['Nodes']['user']['Most Frequently edited POI'] = ob.filter(Q(user=user) & \
			Q(timestamp__range=[start,end]) & Q(feature_type='node')).raw('''SELECT k, v, count(*) \
			as count FROM ( SELECT skeys(tags) AS k, svals(tags) \
			as v, user, timestamp FROM populate_feature) AS t \
			WHERE k='amenity' GROUP BY k, v ORDER BY count DESC LIMIT 1''')
	# user search ways
	if user != None and not foundways:
        	stat['Ways']['user']['OSM Username'] = user
		foundwr = False
		for index, item in enumerate(ws):
			if item[index][0] == user:
				stat['Ways']['user']['rank'] = index 
				break
		if not foundwr:
			stat['Ways']['user']['rank'] = 0
		stat['Ways']['user']['highlighted'] = True
		stat['Ways']['user']['Most Frequently edited POI'] = ob.filter(Q(user=user) & \
			Q(timestamp__range=[start,end]) & \
			Q(feature_type='way')).raw('''SELECT k, v, count(*) \
			as count FROM ( SELECT skeys(tags) AS k, svals(tags) \
			as v, user, timestamp FROM populate_feature) AS t \
			WHERE k='amenity' GROUP BY k, v ORDER BY count DESC LIMIT 1''')
	# wrap it up in a json format
	return JsonResponse(stat)