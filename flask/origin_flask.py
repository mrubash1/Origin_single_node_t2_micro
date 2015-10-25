#!/usr/bin/env python

#150930 Flask Run App

import json, operator, re, os
from cassandra.cluster import Cluster
from flask import Flask, jsonify, render_template, request, make_response
from cassandra.query import SimpleStatement
from sets import Set
from operator import itemgetter

from functools import wraps, update_wrapper
from datetime import datetime

#set up connection to elasticsearch
from elasticsearch import Elasticsearch
#es_public_url= '52.89.66.139'
#es = Elasticsearch([es_public_url]) #has to be public IP, as this t2 micro is spun up on a different AWS account
#elastic_search_index_name='test_150929'
elastic_search_index_name='test_151001'
#es= Elasticsearch(['52.89.66.139'])
es=Elasticsearch(['52.26.246.118'])

def small_ES_dataset():
    elastic_search_index_name='test_151001'
    #es= Elasticsearch(['52.89.66.139'])
    es=Elasticsearch(['52.26.246.118'])
    query_too_large = True
    return query_too_large



# setting up connections to cassandra
from cqlengine import connection
#cassandra_public_url_array=['52.89.66.139','52.89.34.7','52.89.116.45','52.89.78.4', '52.89.27.115','52.89.133.147','52.89.1.48']
cassandra_public_url_array=['52.26.246.118']
cassandra_table='url_ranks_links_23'
#cassandra_table='url_ranks_links_21'
CASSANDRA_KEYSPACE = "test"
connection.setup(cassandra_public_url_array,CASSANDRA_KEYSPACE)
cluster = Cluster(cassandra_public_url_array)
session = cluster.connect(CASSANDRA_KEYSPACE)

#Global variables for functions
max_url_lookups=10000
page_rank_cutoff=0.15
query_too_large=False #instantiate as false to begin with

app = Flask(__name__)

print 'VERIFICATION: SCRIPT RUNNING'
# homepage
@app.route("/")
@app.route("/origin")
@app.route("/origin/index")
def hello():
  return render_template("index.html")

# graph query page
@app.route("/origin/graph")
def graph():
  return render_template("graph_query.html")

#to allow for the website to reload, ala no cache
def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Last-Modified'] = datetime.now()
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
        
    return update_wrapper(no_cache, view)

# get username and return graph
@app.route("/origin/graph", methods=['POST'])
@nocache
def graph_post():
  try:
      search_term = request.form["Visualization_Density"] # get username entered
      print search_term
      density = request.form["year"]
      #UPDATE THE NODES HERE TO INFORM THE PROCESSING SPEED OF THE ELASTICSEARCH AND CASSANDRA QUERIES
      if density=="Max (1000 nodes)":
          nodes = 1000
      elif density=="High (500 nodes)":
          nodes = 500
      elif density=="Medium (200 nodes)":
          nodes = 200
      elif density=="Low (100 nodes)":
          nodes = 100
      elif density=="Very Low (50 nodes)":
          nodes = 50

      #LAUNCH ELASTICSEARCH HYBRID
      query_phrase=search_term
      max_nodes=int(int(nodes)/10)
       #artificially put in

      def elasticsearch(es,query_phrase,index_name):
        #Query Elasticsearch to see what URLs contain this query
        #See how large the index is
        test=es.search(index_name,q='wiki')
        size_total=test['hits']['total']
        #print size_total
        
        #make res global so it can be read in future functions
        global res

        #Query Elasticsearch to see what URLs contain this query, return all elements via size call
        #Return metadata, json format, which includes 'u_id
        res = es.search(index_name, q=query_phrase,fields=[''],size=(size_total))
        
        #Find total amount by query that is a false positive, 100%, wiki search
        total_Hits = (es.search(index_name, q='wiki'))['hits']['total'] #modify later to direct call to get total amount
        positive_hits =res['hits']['total']
        percent_hits= str(100* (float(positive_hits)/float(size_total)))
        #Output
        query_html_printout =  '"' + query_phrase +'" in ' + percent_hits[:5] + '% of wikipedia pages' 
        print query_html_printout
        #return the res elastic search results for future processing
        return res, query_html_printout
        #Use the smaller database that won't cause failure due to RAM constraints

      


      #return the elastic search item
      try:
        res, query_html_printout=elasticsearch(es,query_phrase,elastic_search_index_name)
      except:
        #Use the smaller database that won't cause failure due to RAM constraints
        print 'elastic search results exceed memory, must use smaller database'
        small_ES_dataset()
        res, query_html_printout=elasticsearch(es,query_phrase,elastic_search_index_name)
        print 'The ES search partially fails?'
        pass

      #print res

    # get username and return graph
    #@app.route("/origin/graph", methods=['POST']) #not sure if this needs the post statement
    #def graph_produce(res):
      print ('In GRAPH_PRODUCE LOOP')
      def loop_to_get_links_from_es_query(res):
          query_url_list=[]
          for hit in res['hits']['hits']:
              query_data=json.dumps(hit)
              result = re.search('"_id": "(.*)", "_index":', query_data)
              result = result.group(1)
              #print result
              query_url_list.append(result)
          return query_url_list
          #print 'Length of query_url_list: ', len(query_url_list)

      #return the list of urls corresponding to text search in elastic search
      query_url_list=loop_to_get_links_from_es_query(res)

      #Establish the URL by order according to the query, using the query_url_list
      def extract_queried_urls_ranks_links(query_url_list, session,page_rank_cutoff,max_url_lookups):
          print 'Inside loop: extract_queried_urls_ranks_links'
          #Arrays to fill in
          data_json=[]
          data_json_no_example_links=[]
          url_lookup=0
          for query in query_url_list:
            try:
                #Limit urls analyzed to max prestated amount
                if url_lookup < max_url_lookups:
                  url_lookup+=1
                  key_lookup="'" +  query + "';" #extra parentheses to avoid colon error
                  query1 = "SELECT * FROM " + cassandra_table + " WHERE url="+key_lookup
                  try:
                    rows=(session.execute(query1))             
                    if rows != []:
                      for row in rows:
                          #Create JSON for html insertion, by constructing dictionary for assembly in array 
                          if row[2] > page_rank_cutoff:
                              data_json_sample=({"url": row[0], "rank": row[2], "total_links" : len(row[1]), "example_links" : row[1] })
                              data_json_sample_no_example_links=({"url": row[0], "rank": row[2], "total_links" : len(row[1])})
                              #print data_json_sample['rank']
                              #MAKE SURE TO CONVERT ABOVE FOR THE RANK TO STRING LATER

                              #Fill the array with dicts
                              data_json.append(data_json_sample)
                              #limit the length of the data_json file to total amount of nodes, do every 200
                              if len(data_json) > 200 :
                                  data_json.sort(key=operator.itemgetter('rank'), reverse=True)
                                  del data_json[100:]
                              data_json_no_example_links.append(data_json_sample_no_example_links)
                  except:
                      #print 'inner loop error' 
                      pass
            except:
              pass
          #return information for creating JSON files    
          #See size of max_nodes and if reached
          print 'How many urls analyzed: ', url_lookup
          return data_json, data_json_no_example_links

      #Run extract and keep arrays
      data_json,data_json_no_example_links=extract_queried_urls_ranks_links(query_url_list,session,page_rank_cutoff,max_url_lookups)
      #sort for highest ranks
      json_for_html_table=sorted(data_json, key=itemgetter('rank'), reverse=True)
      #print json_for_html_table


      def prepare_json_for_D3(json_for_html_table,max_nodes):
          print ('prepare_json_for_D3...')
          #Grab a maximum amounts of nodes 
          central_node_limit=max_nodes
          json_for_html_table_top= json_for_html_table[:central_node_limit]
          #print len(json_for_html_table_top)
           
          #create a global counter for creating the d3 objects
          node_counter=0
          central_node_counter=0
          nodes=[]
          links=[]

          #Edge weight currently set to 1, but can be increased in the future
          edge_weight=4
          edge_weight_central_node=1

          #Create the node portion of the graph first so they can be   
          global_counter=0
          central_nodes=[]
          for json_dict in json_for_html_table_top:
              if global_counter < central_node_limit:
                #print ('in the node creation loop')
                #create central_node list to later attach edges
                central_node_locator = json_dict['url']
                central_nodes.append(central_node_locator)
                #get a dict of the node for d3
                #node=({"name": json_dict['url'], "group":0})
                node=({"name": json_dict['url'], "group":0, "rank":json_dict['rank'],"total_links":json_dict['total_links']})
                nodes.append(node)
                #log which node these links will be connected to
                central_node=node_counter
                #then increase node counter to make sure that the links don't override
                node_counter+=1
                #iterate through links file
                global_counter+=1
                #print global_counter
              else:
                break

          #print 'Starting D3 edge creation loop'
          max_links_to_center_node=10
          #reset global counter
          global_counter=0
          #to create D3 graph, loop through each of the dicts in json_for_html_table
          for json_dict in json_for_html_table_top:
              #reset the global counter to twice what it was before, as we already went through once
              if global_counter < central_node_limit:
                #print "MADE IT TO THE BIG LOOP:"
                #log which node these links will be connected to
                central_node=global_counter
                #iterate through links file, but have a counter to set it to a limit
                counter=0
                #remove duplicate links to allow for the graph to assemble correctly
                #LATER COUNT THE DUPLICATES IN THE LIST TO CHANGE THE WEIGHTING OF THE GRAPH
                for link in list(set(json_dict['example_links'])):
                    #print "MADE IT TO THE SMALL LOOP:"
                    #Create a statement to pick 9 nodes randomly before checking for connecting nodes
                    if link in central_nodes:
                        #get the position of link in the central_nodes 
                        central_node_with_edge=central_nodes.index(link)
                        #Create the dict to incorporate
                        #create link list where the source is the current node, target is central node
                        #Value=edge weight, currently set to zero
                        link=({"source": global_counter, "target" : central_node_with_edge, "value":edge_weight_central_node})
                        #print link
                        ##HAVE TO MAKE THIS LINK GO TO A CENTRAL NODE
                        #nodes.append(node)
                        #node_counter+=1
                        links.append(link)
                        counter+=1
                if counter < max_links_to_center_node: # run to make more neighboring nodes
                  for link in list(set(json_dict['example_links'])):
                    if counter < max_links_to_center_node:
                        #Create color coded network around nodes
                        group_color=global_counter%20
                        if group_color == 0: #avoid 0 as that is for the nodes only
                          group_color=19
                        #record the node and link
                        #node=({"name": link, "group":group_color})
                        node=({"name": link, "group":group_color, "rank":'',"total_links":''})
                        #create link list where the source is the current node, target is central node
                        #Value=edge weight, currently set to zero
                        link=({"source": node_counter, "target" : global_counter, "value":edge_weight}) #central node = global counter, and should correspond to central node
                        nodes.append(node)
                        node_counter+=1
                        links.append(link)
                        counter+=1
                        #print 'counter', counter
                        #print 'This is the central node, should be static then increasing: ', central_node
                    
                    else:
                      pass
                global_counter+=1
                #Create D3 graphing object that we will return to the render_template
                D3_graphing_json_sample=({"nodes": nodes, "links": links})
                #print 'completed preperation of D3_graphing_json_sample'
          return D3_graphing_json_sample

      #run functions for getting D3 ready information
      D3_graphing_json_sample= prepare_json_for_D3(json_for_html_table,max_nodes)
      #print D3_graphing_json_sample

      print 'Saving query'
      output_directory = 'static/data'
      if not os.path.exists(output_directory):
        os.makedirs(output_directory)
      #save the file to static/data folder, and convert it to a json file first
      filename= query_phrase  + '_'+'max_nodes' + '_'+elastic_search_index_name+'_'+CASSANDRA_KEYSPACE+'_'+cassandra_table 
      file = open(output_directory+'/graphing_'+filename+'.json', "w")
      file.write(json.dumps(D3_graphing_json_sample))
      file.close()
      #save the rank data for future analysis
      file = open(output_directory+'/analysis_'+filename+'.json', "w")
      file.write(json.dumps(data_json_no_example_links))
      file.close()
      
      print 'About to render template...'
      return render_template("graph_and_table_render.html", query_output= query_html_printout, json_output= json.dumps(D3_graphing_json_sample), output=json_for_html_table[:100]) #make 100 the max nodes
      #return render_template("graph_and_table_render.html", query_output= query_html_printout, json_output= json.dumps(hard_coded_json), output=json_for_html_table[:100]) #make 100 the max nodes

      #return render_template("D3_graph.html", graph_output = D3_graphing_json_sample)
      #return render_template("D3_graph.html")

    #print links_listedPerURL[1]
      # link to the slides
  except:
    if query_too_large == False:
      return render_template("graph-noresult.html", response = 'Error encountered, query not found')  # in case there is no result
    if query_too_large == True:
      return render_template("graph-noresult.html", response = 'Error encountered, query found in >10% of wikipedia pages')  # in case there is no result


@app.route("/origin/slides") 
def slides():
  return render_template("slides.html")

@app.route("/origin/demo")
def demo():
  return render_template("demo.html")

@app.route("/origin/blog")
def blog():
  return redirect("https://github.com/mrubash1/Origin/blob/master/README.md") #update as available



if __name__ == "__main__":
  print 'running'
  app.run(host='0.0.0.0', port = 80)
