import os
import re
import sys
import json
import itertools
from multiprocessing.dummy import Pool as ThreadPool
import pandas as pd
import datetime
import traceback
from kafka import KafkaProducer
try:
    import dataPrepartion.custlogger as logg
except:
    import custlogger as logg

try:
    import dataPrepartion.commonUtil as comUtil
except:
    import commonUtil as comUtil


try:
    import pyspark
except:
    import findspark
    findspark.init()

from pyspark.sql import SparkSession
from pyspark.sql.types import *
from configparser import ConfigParser

# instantiate config Parser
config = ConfigParser()


def logKey(spark, prcId):
    try:
        current_date = str(datetime.datetime.now().strftime("%Y-%m-%d"))
        app_id = spark.sparkContext.getConf().get('spark.app.id')
        app_name = spark.sparkContext.getConf().get('spark.app.name')
        logkey = str(prcId+"-"+app_name+"-"+app_id+"-"+current_date)
        return logkey
    except Exception as e:
        print(str(datetime.datetime.now()) + "____________ Exception occurred in logKey() ________________")
        print("Exception::msg %s" % str(e))
        print(traceback.format_exc())


def publishKafka(producer,spark_logger,prcKey,logLevel,msg):
    try:
        if logLevel == "INFO" or logLevel == "WARN":
            spark_logger.warn(msg)
        else :
            spark_logger.error(msg)     
        jsonString = {"Timestamp":str(datetime.datetime.now()),"LogLevel": logLevel,"LogMsg":msg}
        producer.send(config.get('DIT_Kafka_config', 'TOPIC'), key=prcKey.encode('utf-8'), value=json.dumps(jsonString).encode('utf-8'))
    except Exception as e:
        print(str(datetime.datetime.now()) + "____________ Exception occurred in publishKafka() ________________")
        print("Exception::msg %s" % str(e))
        print(traceback.format_exc())

def prepareTPTScript(spark,srcMap, schemaMap, destMap, queryMap, spark_logger):
    for srcKey, src in srcMap.items():
        spark_logger.warn("The processing singleSrcPrc() process for " + srcKey.split(":")[0])
        #spark_logger.warn("_________________Started processing process Id : " + prcRow['prcId'] + " : ____________________")
        try:
            print("TEST200:", )
            tptFolder = config.get('DIT_setup_config', 'tptFolder')
            print("src Map")
            print(srcMap)
            print("schemaMap")
            print(schemaMap)
            print("destMap")
            print(destMap)
            print("queryMap")
            print(queryMap)
            srcColMap = pd.read_json(config.get('DIT_setup_config', 'srcCols') + 'srcCols_' + srcKey.split(":")[0] + '.json')
            print(srcColMap)
            destColMap = pd.read_json(config.get('DIT_setup_config', 'destCols') + 'destCols_' + srcKey.split(":")[1] + '.json')
            print(destColMap)
            #fname = tptFolder + PrcName + ".tpt"
            #print("TEST201:" + fname)
            #f_tpt = open(fname, "w")
    
            #f_tpt.write(ProcName)
            #f_tpt.write("\n")
    
    
        #f_tpt.close()

        except Exception as e:
            spark_logger.warn(str(datetime.datetime.now()) + "____________ Exception occurred in prepareTPTScript() ________________")
            spark_logger.warn(str(datetime.datetime.now()) + " The exception occurred for process ID :: " + srcKey)
            spark_logger.warn("Exception::msg %s" % str(e))  
            print(traceback.format_exc())


def fixedWidthProcessor(src,schemaStruct,spark,key,producer, spark_logger):
    try:
        recordSize=src.get('recordSize')[0].item() if src.get('recordSize') is not None else 0                
        posColmap={}
        posLenMap={}
        for strctFld in schemaStruct:
            #print(strctFld.jsonValue())
            posLenMap[strctFld.jsonValue()['metadata']['colPos']]=strctFld.jsonValue()['metadata']['length']
            posColmap[strctFld.jsonValue()['metadata']['colPos']]=strctFld.jsonValue()['name']
        #print(posLenMap) 
        reglst=[]
        itmlst=[]
        for colPos,length in sorted(posLenMap.items()):
            reglst.append("(.{"+str(length)+"})")
            itmlst.append("$"+str(colPos)+"^")
        regexExpr= ''.join(reglst)
        itemExpr= ''.join(itmlst)  
        #print(regexExpr)
        #print(itemExpr)
        collst=[]
        for colPos,colName in sorted(posColmap.items()):
            collst.append("trim(splitcol["+str(colPos-1)+"]) as "+colName)
        colExpr= ','.join(collst) 
        #print(colExpr)   
        #query="select split(regexp_replace(value, '{}','{}'),'\\\^') from fixedWidth_"+src['srcId'].any()
        query="split(regexp_replace(value, '{}','{}'),'\\\^') as splitcol"
        #print(query.format(regexExpr,itemExpr[:-1]))
        ## Comment the above line till fldNames and uncomment the previous approach in future releases.
        fxdwdthDf=None
        if recordSize == 0 :            
            fxdwdthDf=spark.read.text(src['srcLocation'].any())
        else :
            fxdwdthDf=spark.read.text(src['srcLocation'].any()).filter("length(value) = "+str(recordSize))                
        fxdwdthDf.show(truncate=False)
        splitColDf=fxdwdthDf.selectExpr(query.format(regexExpr,itemExpr[:-1])) #.write.saveAsTable('fixedWidth_'+src['srcId'].any())                              
        finDf=splitColDf.selectExpr(collst)
        return finDf
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in fixedWidthProcessor()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key is :: " + src['srcId'].any())
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())
    


def findMapping(uniqSrc,uniqDest,key,producer,spark_logger):
    try:
        if uniqSrc == 1 and uniqDest == 1:
            return "One_to_One"
        elif uniqSrc > 1 and uniqDest == 1:
            return "Many_to_One"
        elif uniqSrc == 1 and uniqDest > 1:
            return "One_to_Many"
        elif uniqSrc > 1 and uniqDest > 1:
            return "Many_to_Many"
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in findMapping()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The exception occurred for :: " + uniqSrc+" :: "+uniqDest)
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())
        
        
def prepareJoinCodition(joinCondition,srcDest,prcRow,srcColMap,key,producer,spark_logger):
    try:
        for row in prcRow['joinCol'].split("=") :
            if srcDest.split(":")[0] in row.split(":")[0] :
                srcCol = srcColMap[(srcColMap['srcId'] == srcDest.split(":")[0]) & (srcColMap['colId'] == int(row.split(":")[1]))]
                #print(srcDest.split(":")[0]+"."+srcCol['colName'].str.cat())
                if "=" not in joinCondition :
                    joinCondition += srcDest.split(":")[0]+" inner join {tab} on "+srcDest.split(":")[0]+"."+srcCol['colName'].str.cat()+" = {col}"
                    #joinCondition.format(tab1=srcDest.split(":")[0],col1= srcDest.split(":")[0]+"."+srcCol['colName'].str.cat()+"=")
                else :
                    #joinCondition += srcDest.split(":")[0]+"."+srcCol['colName'].str.cat()
                    joinCondition=joinCondition.format(tab = srcDest.split(":")[0], col = srcDest.split(":")[0]+"."+srcCol['colName'].str.cat())
        return joinCondition            
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in prepareJoinCodition()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key is :: " + srcDest)
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())
         


def prepareFilterCodition(srcDest,prcRow,srcColMap,key,producer,spark_logger):
    try:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Processing filter condition for "+srcDest)
        for row in prcRow['filterCondition'].split("@") :
            if srcDest.split(":")[0] in row.split(":")[0] :
                #Fetch the column details from src col mapping having same srcID and ColID
                srcCol = srcColMap[(srcColMap['srcId'] == srcDest.split(":")[0]) & (srcColMap['colId'] == int(row.split(":")[1]))]
                return " Where "+srcDest.split(":")[0]+"."+srcCol['colName'].str.cat()+ prcRow['filterCondition'].split("@")[1]
            else :
                return ""            
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in prepareFilterCodition()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key is :: " + srcDest)
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())


                        
def singleSrcPrc(spark,srcMap, schemaMap, destMap, queryMap,filterCondition,partitionByMap,key,producer, spark_logger):
    for srcKey, src in srcMap.items():
        try:
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","The processing singleSrcPrc() process for " + srcKey)
            if  src['fileType'].any() == "json" or src['fileType'].any() == "parquet" or src['fileType'].any() == "orc":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                #inputLoc=comUtil.moveToHDFS(src['srcLocation'].any(),config.get('DIT_setup_config', 'ditInputFolder')+key+"/"+srcKey.split(":")[0])
                df = spark.read.format(src['fileType'].any()).schema(schemaMap[srcKey]).load(src['srcLocation'].any())
                #.option("inferSchema", src.get('inferSchema').str.cat().lower()) Not required
            elif src['fileType'].any() == "csv" or src['fileType'].any() == "delimited":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                if src.get('delimiter') is None :
                    delimiter=","
                else :
                    delimiter=src.get('delimiter').str.cat()
                if src.get('quote') is None :
                    quote="\""
                else :
                    quote=src.get('quote').str.cat()
                if src.get('inferSchema') is None or src.get('inferSchema').str.cat().lower() == "false" :
                    df = spark.read.format("csv").schema(schemaMap[srcKey]).option("header", src['header'].any()).option("delimiter", delimiter).option("quote", quote).load(src['srcLocation'].any())
                else:
                    df = spark.read.format("csv").option("header", src['header'].any()).option("delimiter", delimiter).option("quote", quote).option("inferSchema", src.get('inferSchema').str.cat().lower()).load(src['srcLocation'].any())
            elif src['fileType'].any() == "fixedWidth":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                df=fixedWidthProcessor(src,schemaMap[srcKey],spark,key,producer, spark_logger)
                df.show(truncate=False)
            elif src['fileType'].any() == "hivetable":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from table "+src["table"].any())
                ##TODO fieldNames() will be available in verions 2.3.0 onwards ( https://jira.apache.org/jira/browse/SPARK-20090)
                #colName = ','.join(schemaMap[srcKey].fieldNames())
                #Using alternate approach to fieldNames() until then
                fldNames=[]
                for strctFld in schemaMap[srcKey]:
                    fldNames.append(strctFld.jsonValue()['name'])
                colName = ','.join(fldNames)    
                ## Comment the above line till fldNames and uncomment the previous approach in future releases.
                df = spark.sql('SELECT ' + colName + ' FROM ' + src["table"].any())
                print("read from table" + src["table"].any())
            elif src['fileType'].any() == "jdbcclient":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from table "+src["table"].any())
                df = spark.read.format("jdbc").option("url", src["url"].any()).option("driver",src["driver"].any()).option("dbtable", src["table"].any()).option("user", src["user"].any()).option("password", src["password"].any()).load()
            #df.show()
            #df.printSchema()  
            df.createOrReplaceTempView(srcKey.split(":")[0])
            #Publishing statistics of source data set
            srcSummary=df.describe().toJSON().collect()
            srcJsons=[]
            for dfele in srcSummary:
                srcJsons.append(json.loads(dfele))
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","The summary of source "+srcKey.split(":")[0]+" is : " + json.dumps(srcJsons))
        except Exception as e:
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in singleSrcPrc()")
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key for srcMap is :: " + srcKey)
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())

            
        for destKey, dest in destMap.items():
            #print(queryMap[destKey])
            #print(','.join(queryMap[destKey]))
            try:
                #Fetch value of compression
                if dest.get('compression') is None :
                    compression="none"
                else :
                    compression=dest.get('compression').str.cat() 
                #Fetch value of numPartitions of DF 
                if dest.get('numPartitions') is None :
                    numPartitions=8
                else :
                    numPartitions=dest.get('numPartitions')[0].item()  
                    
                #Fetch value of compression
 
                
                dfWrite=spark.sql("select "+','.join(queryMap[destKey])+" from "+destKey.split(":")[0]+filterCondition)    
                    
                if dest['fileType'].any() == "csv" or dest['fileType'].any() == "json" or dest[
                    'fileType'].any() == "orc" or dest['fileType'].any() == "parquet":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " at "+dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest[
                                "fileType"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.coalesce(numPartitions).write.mode(dest["mode"].any()).format(dest["fileType"].any())\
                        .option("compression",compression)\
                        .save(dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest["fileType"].any())
                    else :
                        print(partitionByMap)
                        dfWrite.coalesce(numPartitions).write.partitionBy(partitionByMap[destKey])\
                        .mode(dest["mode"].any()).format(dest["fileType"].any())\
                        .option("compression",compression)\
                        .save(dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest["fileType"].any())
                            
                    
                    #spark.sql("select "+','.join(queryMap[destKey])+" from "+destKey.split(":")[0]+filterCondition).show(truncate=False)
                    #df.selectExpr(queryMap[destKey]).show(truncate=False)
                elif dest['fileType'].any() == "hivetable":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " having table name : "+dest["table"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.write.mode(dest["mode"].any()).saveAsTable(dest["table"].any())
                    else :
                        dfWrite.write.partitionBy(partitionByMap[destKey]).mode(dest["mode"].any()).saveAsTable(dest["table"].any())  
                elif dest['fileType'].any() == "jdbcclient":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " having table name : "+dest["table"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.coalesce(numPartitions).write.format("jdbc").mode(dest["mode"].any())\
                        .option("url", dest["url"].any()).option("driver", dest["driver"].any())\
                        .option("dbtable",dest["table"].any()).option("user",dest["user"].any())\
                        .option("password", dest["password"].any()).save()
                    else :
                        dfWrite.coalesce(numPartitions).write.partitionBy(partitionByMap[destKey]).format("jdbc").mode(dest["mode"].any())\
                        .option("url", dest["url"].any()).option("driver", dest["driver"].any())\
                        .option("dbtable",dest["table"].any()).option("user",dest["user"].any())\
                        .option("password", dest["password"].any()).save()
                            
                elif dest['fileType'].any() == "DataBase":
                    print("TEST107c::")
                    prepareTPTScript(spark,srcMap, schemaMap, destMap, queryMap, producer,spark_logger)

                #Publishing statistics of destination data set
                destSummary=dfWrite.describe().toJSON().collect()
                destJsons=[]
                for dfele in destSummary:
                    destJsons.append(json.loads(dfele))
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","The summary of destination data set "+destKey.split(":")[1]+" is : " + json.dumps(destJsons))
            except Exception as e:
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in singleSrcPrc()")
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key for target Map is :: " + destKey)
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())

    
def multiSrcPrc(spark,srcMap, schemaMap, destMap, queryMap,joinCondition,filterCondition,partitionByMap,key, producer,spark_logger):
    for srcKey, src in srcMap.items():
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","In multiSrcPrc() method processing for Src Id " + srcKey)
        try:
            if  src['fileType'].any() == "json" or src['fileType'].any() == "parquet" or src['fileType'].any() == "orc":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                df = spark.read.format(src['fileType'].any()).schema(schemaMap[srcKey]).load(src['srcLocation'].any())
                #.option("inferSchema", src.get('inferSchema').str.cat().lower()) Not required
            elif src['fileType'].any() == "csv" or src['fileType'].any() == "delimited":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                if src.get('delimiter') is None :
                    delimiter=","
                else :
                    delimiter=src.get('delimiter').str.cat()

                if src.get('quote') is None :
                    quote="\""
                else :
                    quote=src.get('quote').str.cat()
                if src.get('inferSchema') is None or src.get('inferSchema').str.cat().lower() == "false" :
                    df = spark.read.format("csv").schema(schemaMap[srcKey]).option("header", src['header'].any()).option("delimiter", delimiter).option("quote", quote).load(src['srcLocation'].any())
                else:
                    df = spark.read.format("csv").option("header", src['header'].any()).option("delimiter", delimiter).option("quote", quote).option("inferSchema", src.get('inferSchema').str.cat().lower()).load(src['srcLocation'].any())
            elif src['fileType'].any() == "fixedWidth":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from "+src['srcLocation'].any())
                df=fixedWidthProcessor(src,schemaMap[srcKey],spark,key,producer, spark_logger)                
                df.show(truncate=False)
            elif src['fileType'].any() == "hivetable":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from table "+src["table"].any())
                ##TODO fieldNames() will be available in verions 2.3.0 onwards ( https://jira.apache.org/jira/browse/SPARK-20090)
                #colName = ','.join(schemaMap[srcKey].fieldNames())
                #Using alternate approach to fieldNames() until then
                fldNames=[]
                for strctFld in schemaMap[srcKey]:
                    fldNames.append(strctFld.jsonValue()['name'])
                colName = ','.join(fldNames)    
                ## Comment the above line till fldNames and uncomment the previous approach in future releases.
                df = spark.sql('SELECT ' + colName + ' FROM ' + src["table"].any())
            elif src['fileType'].any() == "jdbcclient":
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Reading data in format : "+src['fileType'].any()+" for source "+ src['srcId'].any() +"  from table "+src["table"].any())
                df = spark.read.format("jdbc").option("url", src["url"].any()).option("driver",src["driver"].any()).option("dbtable", src["table"].any()).option("user", src["user"].any()).option("password", src["password"].any()).load()
            df.show()
            df.printSchema()  
            df.createOrReplaceTempView(srcKey.split(":")[0])
        except Exception as e:
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in multiSrcPrc()")
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key for srcMap is :: " + srcKey)
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())
            
    queryExpr=""
    #List to keep track of unique destination for publishing
    distinctDest=[]  
    if joinCondition == "NA" and filterCondition == "NA" :
        #Should iterate only once as query is being provided
        for qkey, queryStr in queryMap.items():
            queryExpr=queryStr[0]
    else :
        query="select "    
        for qkey, querylst in queryMap.items():
            query+=','.join(querylst)+","
        queryExpr=query[0:-1]+joinCondition+filterCondition
        
            
    for destKey, dest in destMap.items():
        if destKey.split(":")[1] not in distinctDest :
            distinctDest.append(destKey.split(":")[1])
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing the records for Dest Id :: "+destKey.split(":")[1])
            #Fetch value of compression
            if dest.get('compression') is None :
                compression="none"
            else :
                compression=dest.get('compression').str.cat() 
            #Fetch value of numPartitions
            if dest.get('numPartitions') is None :                 
                numPartitions=8
            else :
                numPartitions=dest.get('numPartitions')[0].item()
            print(partitionByMap[destKey])     
            try:
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO",":::::Executing Query::::::"+queryExpr)
                dfWrite=spark.sql(queryExpr)                
                if dest['fileType'].any() == "csv" or dest['fileType'].any() == "json" or dest['fileType'].any() == "orc" or dest['fileType'].any() == "parquet":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " at "+dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest[
                                "fileType"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.coalesce(numPartitions).write.mode(dest["mode"].any()).format(dest["fileType"].any())\
                        .option("compression",compression)\
                        .save(dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest["fileType"].any())  
                    else :
                        dfWrite.coalesce(numPartitions).write.partitionBy(partitionByMap[destKey]).mode(dest["mode"].any()).format(dest["fileType"].any())\
                        .option("compression",compression)\
                        .save(dest["destLocation"].any() + dest["destId"].any() + "_" + dest["fileType"].any() + "/" + dest["fileType"].any())      
                    
                    dfWrite.show(truncate=False)                 
                    #spark.sql(query[0:-1]+joinCondition+filterCondition).show(truncate=False)
                elif dest['fileType'].any() == "hivetable":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " having table name : "+dest["table"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.write.mode(dest["mode"].any()).saveAsTable(dest["table"].any())
                    else :
                        dfWrite.write.partitionBy(partitionByMap[destKey]).mode(dest["mode"].any()).saveAsTable(dest["table"].any())    
                elif dest['fileType'].any() == "jdbcclient":
                    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Publishing data in fromat : "+dest['fileType'].any()+" in mode :"+dest["mode"].any() + " having table name : "+dest["table"].any())
                    if dest.get('partitionBy') is None :
                        dfWrite.coalesce(numPartitions).write.format("jdbc").mode(dest["mode"].any())\
                        .option("url", dest["url"].any()).option("driver", dest["driver"].any())\
                        .option("dbtable",dest["table"].any()).option("user",dest["user"].any())\
                        .option("password", dest["password"].any()).save()
                    else :
                        dfWrite.coalesce(numPartitions).write.partitionBy(partitionByMap[destKey]).format("jdbc").mode(dest["mode"].any())\
                        .option("url", dest["url"].any()).option("driver", dest["driver"].any())\
                        .option("dbtable",dest["table"].any()).option("user",dest["user"].any())\
                        .option("password", dest["password"].any()).save()                            
                elif dest['fileType'].any() == "DataBase":
                    print("TEST107c::")
                    prepareTPTScript(spark,srcMap, schemaMap, destMap, queryMap,producer, spark_logger)   
                         
            except Exception as e:
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in multiSrcPrc()")
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The iteration key for target Map is :: " + destKey)
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
                comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())
        
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Published the records for Dest Ids :: "+' '.join(distinctDest))
        
def prepareMeta(sprkSession, prcRow,key,producer,spark_logger):
    possibleError=""
    #key=logKey(sprkSession, prcRow['prcId'])
    #spark_logger = logg.Log4j(sprkSession,key)
    #spark_logger.warn("_________________Started processing process Id : " + prcRow['prcId'] + " : ____________________")
    try:
        #comUtil.publishKafka(producer,spark_logger,key,"INFO","Started processing process Id : "+prcRow['prcId'])
        queryMap = {}
        schemaMap = {}
        srcMap = {}
        destMap = {}
        partitionByMap={}
        #joinCondition=" from {tab1} inner join {tab2} on {col1} = {col2}"
        joinCondition=" from "
        filterCondition= ""
        
        # Fetch process Id specific mapping file
        maps = pd.read_json(config.get('DIT_setup_config', 'prcMapping') + 'colMapping_' + prcRow['mapId'] + '.json')
        mapTab = maps[maps['mapId'] == prcRow['mapId']]
        for mapId, mapRow in mapTab.iterrows():
            # Fetch source and destination column mapping files with respect to each source and column 
            srcColMap = pd.read_json(config.get('DIT_setup_config', 'srcCols') + 'srcCols_' + mapRow['srcId'] + '.json')
            destColMap = pd.read_json(config.get('DIT_setup_config', 'destCols') + 'destCols_' + mapRow['destId'] + '.json')
            srcCol = srcColMap[(srcColMap['srcId'] == mapRow['srcId']) & (srcColMap['colId'] == mapRow['srcColId'])]
            destCol = destColMap[(destColMap['destId'] == mapRow['destId']) & (destColMap['colId'] == mapRow['destColId'])]
            # query.append(srcCol['colName'].str.cat()+" as "+destCol['colName'].str.cat())
            srcDest = mapRow['srcId'] + ":" + mapRow['destId']
            query= []
            if srcCol.empty :
                possibleError="\n 1.Default column is not set in Destination \n 2.Process mapping maps to a source column that does not exist"
                query.append("cast(" + destCol['default'].astype(str).str.cat() + " as " + destCol['colType'].str.cat() + " ) as " + destCol['colName'].str.cat())
            elif destCol.get('transFunc') is None or destCol.get('transFunc').empty or destCol.get('transFunc').isnull().any().any() or destCol.get('transFunc').item()== "NA":
                query.append("cast(" +mapRow['srcId'] +"." + srcCol['colName'].str.cat() + " as " + destCol['colType'].str.cat() + " ) as " + destCol['colName'].str.cat())
            else :
                query.append("cast(" + destCol['transFunc'].str.cat().format(mapRow['srcId'] +"." +srcCol['colName'].str.cat())+  " as " + destCol['colType'].str.cat() + " ) as " + destCol['colName'].str.cat())
            
            #For every src:key pair create a SQL query map
            if srcDest not in queryMap :
                queryMap[srcDest] = query
            else :
                tmpQuery = queryMap[srcDest]
                tmpQuery.extend(query)
                queryMap[srcDest] = tmpQuery

            ## Fetch schema of the sources
            if srcDest not in schemaMap:
                fields = fetchSchema(srcColMap[srcColMap['srcId'] == mapRow['srcId']],key,producer, spark_logger)
                schema = StructType(fields)
                schemaMap[srcDest] = schema
                # Fetch source and destination details
                src = pd.read_json(config.get('DIT_setup_config', 'srcDetails') + 'src_' + mapRow['srcId'] + '.json')
                dest = pd.read_json(config.get('DIT_setup_config', 'destDetails') + 'dest_' + mapRow['destId'] + '.json')
                srcMap[srcDest] = src[src['srcId'] == mapRow['srcId']]
                destMap[srcDest] = dest[dest['destId'] == mapRow['destId']]
                #Set join condition  
                if prcRow.get('joinCol') is not None:              
                    joinCondition=prepareJoinCodition(joinCondition,srcDest,prcRow,srcColMap,key,producer,spark_logger)
                #TODO device a logic to seperately write filter queries 
                if prcRow.get('filterCondition') is not None:     
                    filterCondition+=prepareFilterCodition(srcDest, prcRow, srcColMap,key,producer,spark_logger)
                
                if dest.get('partitionBy') is None :
                    partitionByMap[srcDest] = "NA"
                else :
                    partCol = destColMap[(destColMap['destId'] == dest.get('partitionBy').str.cat().split(":")[0]) & (destColMap['colId'] == int(dest.get('partitionBy').str.cat().split(":")[1]))]
                    partitionByMap[srcDest] =  partCol['colName'].str.cat()  
                    print(partCol) 
                    print(partitionByMap)
        #Identify the process mapping     
        mapping=findMapping(mapTab.srcId.nunique(),mapTab.destId.nunique(),key,producer,spark_logger)
        #Process data 
        processData(sprkSession,mapping, srcMap, schemaMap, destMap, queryMap,joinCondition,filterCondition,partitionByMap,key,producer, spark_logger)
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in prepareMeta()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The exception occurred for process ID :: " + prcRow['prcId'])
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The possible errors can be "+possibleError)
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())


def executeQuery(sprkSession, prcRow,key,producer,spark_logger):
    possibleError=""
    try:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Started processing process Id : "+prcRow['prcId'] + " with SQL query provided")
        queryMap = {}
        schemaMap = {}
        srcMap = {}
        destMap = {}
        partitionByMap={}
        #joinCondition=" from {tab1} inner join {tab2} on {col1} = {col2}"
        joinCondition="NA"
        filterCondition= "NA"
        # Fetch process Id specific mapping file
        maps = pd.read_json(config.get('DIT_setup_config', 'prcMapping') + 'colMapping_' + prcRow['mapId'] + '.json')
        mapTab = maps[maps['mapId'] == prcRow['mapId']]
        srclst = []
        deslst = []
        for src in mapTab['srcId'].tolist():
            srclst+=src
        for dest in mapTab['destId'].tolist():
            deslst+=dest
        srcDestSet=set(itertools.product(srclst,deslst))
        #print(srcDestSet)
        for row in srcDestSet:
            srcDest = row[0] + ":" + row[1]
            # Fetch source and destination column mapping files with respect to each source and column 
            srcColMap = pd.read_json(config.get('DIT_setup_config', 'srcCols') + 'srcCols_' + row[0] + '.json')
            destColMap = pd.read_json(config.get('DIT_setup_config', 'destCols') + 'destCols_' + row[1] + '.json')
            # query.append(srcCol['colName'].str.cat()+" as "+destCol['colName'].str.cat())
         

            ## Fetch schema of the sources
            if srcDest not in schemaMap:
                fields = fetchSchema(srcColMap[srcColMap['srcId'] == row[0]],key,producer, spark_logger)
                schema = StructType(fields)
                schemaMap[srcDest] = schema
                # Fetch source and destination details
                src = pd.read_json(config.get('DIT_setup_config', 'srcDetails') + 'src_' + row[0] + '.json')
                dest = pd.read_json(config.get('DIT_setup_config', 'destDetails') + 'dest_' + row[1] + '.json')
                srcMap[srcDest] = src[src['srcId'] == row[0]]
                destMap[srcDest] = dest[dest['destId'] == row[1]]
                #Add Query
                queryMap[srcDest] =  mapTab['query'] 
                # Add partition info
                if dest.get('partitionBy') is None :
                    partitionByMap[srcDest] = "NA"
                else :
                    partCol = destColMap[(destColMap['destId'] == dest.get('partitionBy').str.cat().split(":")[0]) & (destColMap['colId'] == int(dest.get('partitionBy').str.cat().split(":")[1]))]
                    partitionByMap[srcDest] =  partCol['colName'].str.cat()  
                    print(partCol) 
                    print(partitionByMap)
        #Identify the process mapping     
        mapping=findMapping(len(srclst),len(deslst),key,producer,spark_logger)
        #Process data 
        processData(sprkSession,mapping, srcMap, schemaMap, destMap, queryMap,joinCondition,filterCondition,partitionByMap,key,producer, spark_logger)
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in executeQuery()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The exception occurred for process ID :: " + prcRow['prcId'])
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The possible errors can be "+possibleError)
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())

                
def fetchSchema(srcCols,key, producer,spark_logger):
    try:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Fetching schema values for SRC Id " + srcCols['srcId'].any())
        fields = []
        for idx, clm in srcCols.iterrows():
            colPos= clm.get('colPos') if clm.get('colPos') is not None else "NA"
            length= clm.get('length') if clm.get('length') is not None else "NA"
            if clm['colType'].lower() == "String".lower():
                colField = StructField(name=clm['colName'], dataType=StringType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Int".lower():
                colField = StructField(name=clm['colName'], dataType=IntegerType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Long".lower():
                colField = StructField(name=clm['colName'], dataType=LongType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Float".lower():
                colField = StructField(name=clm['colName'], dataType=FloatType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Double".lower():
                colField = StructField(name=clm['colName'], dataType=DoubleType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Boolean".lower():
                colField = StructField(name=clm['colName'], dataType=BooleanType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            elif clm['colType'].lower() == "Timestamp".lower():
                colField = StructField(name=clm['colName'], dataType=TimestampType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
            else:
                colField = StructField(name=clm['colName'], dataType=StringType(), nullable=eval(clm['isNullable']),metadata={'colPos': colPos,'length':length})
                fields.append(colField)
        return fields
    except Exception as e:
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception occurred in fetchSchema()")
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR"," The exception occurred for Src Id :: " + srcCols['srcId'].str.cat())
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR","Exception::msg %s" % str(e))
        comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"ERROR",traceback.format_exc())


def processData(spark,mapping, srcMap, schemaMap, trgtMap, queryMap,joinCondition,filterCondition,partitionByMap, key,producer,spark_logger):
    # TODO find alternative to any and restrict it to one row using tail head etc
    comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","The process mapping of the current process is :: " +mapping)
    if mapping== "One_to_One" or mapping== "One_to_Many":
        singleSrcPrc(spark,srcMap, schemaMap, trgtMap, queryMap,filterCondition,partitionByMap,key,producer, spark_logger)
    elif mapping == "Many_to_One"  :
        multiSrcPrc(spark,srcMap, schemaMap, trgtMap, queryMap,joinCondition,filterCondition,partitionByMap,key,producer, spark_logger)
    elif mapping == "Many_to_Many" :
        print("in "+mapping)



def processFiles(argTuple):
    # spark = pyspark.sql.SparkSession.builder.appName("DataIngestion").enableHiveSupport().getOrCreate()
    try:
        prc = pd.read_json(argTuple[0])
        #instantiate Kafka Producer
        producer = KafkaProducer(bootstrap_servers=config.get('DIT_Kafka_config', 'KAFKA_BROKERS').split(','),api_version=eval(config.get('DIT_Kafka_config', 'API_VERSION')))
        for prcIdx, prcRow in prc[prc['isActive'] == "True"].iterrows():
            key=logKey(argTuple[1], prcRow['prcId'])
            spark_logger = logg.Log4j(argTuple[1],key)
            startTS=datetime.datetime.now().replace(microsecond=0)
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Started processing "+prcRow['prcId']+" at "+str(startTS))
            if prcRow.get('queryProvided') == "True" :
                executeQuery(argTuple[1], prcRow,key,producer,spark_logger)                
            else :
                prepareMeta(argTuple[1], prcRow,key,producer,spark_logger)
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Finished processing "+prcRow['prcId']) 
            comUtil.publishKafka(producer, config.get('DIT_Kafka_config', 'TOPIC'),spark_logger,key,"INFO","Total time taken to process "+prcRow['prcId']+" is "+ str(datetime.datetime.now().replace(microsecond=0)-startTS))       
    except Exception as e:
            print(str(datetime.datetime.now()) + "____________ Exception occurred in processFiles() ________________")
            print(str(datetime.datetime.now()) + " The exception occured for :: " + argTuple[0])
            print("Exception::msg %s" % str(e))        
            print(traceback.format_exc())


def main(configPath, prcPattern,pool):
    # parse existing file
    config.read(configPath)
    # Read Process files and set thread pool
    prcList = list()
    for dir, root, files in os.walk(config.get('DIT_setup_config', 'prcDetails')):
        matches = re.finditer(r'{0}'.format(prcPattern), ' '.join(files), re.MULTILINE)
        for matchNum, match in enumerate(matches):
            prcList.append(os.path.join(dir, match.group()))
    
    threadPool = ThreadPool(pool)
    print("List of process files to be processed are :: \n", prcList)
    spark = pyspark.sql.SparkSession.builder.appName("DataIngestion").enableHiveSupport().getOrCreate()
    
    threadPool.map(processFiles, zip(prcList, itertools.repeat(spark.newSession())))
    # spark.stop()





#if __name__ == "__main__":
#    prcs="prc_PrcId_[0-9].json"
#    pool=3
#    sys.exit(main('C:\\Users\\sk250102\\Documents\\Teradata\\DIT\\DataIngestionTool\\config\\config.cnf', prcs,pool))


