from __main__ import app
from flask import Flask, render_template, request, jsonify
import os
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType,TimestampType
from pyspark.sql.functions import col, date_trunc
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.functions import col, hour, minute, expr,first,last,max,min,sum,window
from pyspark.sql.functions import col, date_format
from flask import session, url_for, redirect, render_template, request, abort, Response
import talib


stock_data = {}
schema = {'date': 'datetime64[ns]', 'open': DoubleType, 'close': DoubleType, 'high': DoubleType,'low':DoubleType,'volume':int}

@app.route("/")
def home():
    ingest_data()
    return render_template("home.html")

@app.route("/ingest_data")
def ingest_data():
    spark = SparkSession.builder.appName("Nifty100_Data_Load").getOrCreate()
    # spark.conf.set('spark.sql.execution.arrow.enabled', 'true')
    directory_path = 'Nifty100'  # Update this with the actual path to your CSV files

    # List all files in the directory
    file_list = os.listdir(directory_path)
    columns_to_select = ["date","open", "close", "high","low","volume"]
    w1 = Window.partitionBy('date').orderBy('date').rowsBetween(Window.unboundedPreceding,0)
    w2 = w1.rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)

    # Iterate through the files
    for file_name in file_list:
        if file_name.endswith('.csv'):
            file_path = os.path.join(directory_path, file_name)
            df = spark.read.csv(file_path,header = True, inferSchema=True)
            df = df.select(columns_to_select)
            file_name_ind = file_name.split("_")[0]
            # df = df.repartition(10)
            rounded_df = df.withColumn("date", date_trunc("minute", col("date")))
            df_no_duplicates = rounded_df.dropDuplicates(subset=["date"]).orderBy("date")

            #filter dataframe between time 9:15am to 3:30 pm
            filtered_df = df_no_duplicates.filter(
            ((hour(col("date")) > 9) & (hour(col("date")) < 15)) |
            ((hour(col("date")) == 9) & (minute(col("date")) >= 15)) |
            ((hour(col("date")) == 15) & (minute(col("date")) <= 30))
            )

            #clean the dataframe by forward filling the missing values using window function
            df_cleaned = filtered_df\
            .withColumn('open', F.coalesce(F.last('open', True).over(w1),F.first('open',True).over(w2)))\
            .withColumn('close', F.coalesce(F.last('close', True).over(w1),F.first('close',True).over(w2)))\
            .withColumn('high', F.coalesce(F.last('high', True).over(w1),F.first('high',True).over(w2)))\
            .withColumn('low', F.coalesce(F.last('low', True).over(w1),F.first('low',True).over(w2)))\
            .withColumn('volume', F.coalesce(F.last('volume', True).over(w1),F.first('volume',True).over(w2)))

            stock_data[file_name_ind] = df_cleaned  # Assign the DataFrame to a dictionary  with the file name
            break
    # spark.stop()
    return "data ingested"


def aggregate_stock(stock,interval):
    # stock_data = load_all_csv_files()
  
    print(interval)
    df_spark = stock_data[stock]
    
    #aggregate the spark dataframe on the candle interval specified

    # Aggregate the candlestick data using the window specification
    aggregated_df_spark = df_spark.groupBy(
        window("date", interval).alias("date")
    ).agg(
        first("open").alias("open"),
        last("close").alias("close"),
        max("high").alias("high"),
        min("low").alias("low"),
        sum("volume").alias("volume")
    )
    # aggregated_df_spark.printSchema()
    aggregated_df_spark = aggregated_df_spark.withColumn("date",aggregated_df_spark["date"]["end"])
    aggregated_df_spark = aggregated_df_spark.orderBy("date")
    # aggregated_df_spark.show(truncate=False)
    
    aggregated_df_spark = aggregated_df_spark.withColumn("date", date_format(col("date"), "yyyy-MM-dd HH:mm:ss"))
    df_pandas = aggregated_df_spark.toPandas()
    df_pandas["date"]=pd.to_datetime(df_pandas["date"])
    df_pandas["date_index"] = df_pandas["date"]
    df_pandas.set_index('date_index', inplace=True)
    # Here, you can process and display the DataFrame as needed
    return df_pandas  # Display the DataFrame as an HTML table
   

@app.route('/get_stock_data', methods=['POST'])
def get_stock_data():
    stock_name = request.form.get('stockName')
    candle_interval = request.form.get('candleInterval')
    # stock_data = load_all_csv_files()
    if stock_name in stock_data:
        df = aggregate_stock(stock_name, candle_interval)
        print(df)
        
        chart_data = {
        "Date": df["date"].tolist()[:100],
        "Open": df["open"].tolist()[:100],
        "Close": df["close"].tolist()[:100],
        "High": df["high"].tolist()[:100],
        "Low": df["low"].tolist()[:100],
        }
        
        return chart_data
        
        
    else:
        print("Invalid stock name")
        return {}


def technical_indicator(ind,stock_name,candle_interval):
    
    df = aggregate_stock(stock_name, candle_interval)

    if ind=="adx":
        result = talib.ADX(df['high'],df['low'],df["close"])
    
    elif ind=="ao":
        result = talib.AOSC(df['high'],df['low'])
    
    elif ind=="aroon":
        result = talib.AROON(df['high'],df['low'])

    elif ind=="atr":
        result = talib.ATR(df['high'],df['low'],df["close"])

    elif ind=="cci":
        result = talib.CCI(df['high'],df['low'],df["close"])
    

    elif ind=="chop":
        result = talib.CHOP(df['high'],df['low'],df["close"])

    elif ind=="ema":
        result = talib.EMA(df["close"])

    elif ind=="hma":
        result = talib.HMA(df["close"])

    elif ind=="ichimoku":
        result = talib.ichimoku(df['high'],df['low'],df["close"])

    elif ind=="macd":
        result = talib.MACD(df["close"])

    elif ind=="mom":
        result = talib.MOM(df["close"])

    elif ind=="rsi":
        result = talib.RSI(df["close"])

    elif ind=="sma":
        result = talib.SMA(df["close"])

    elif ind=="uo":
        result = talib.ULTOSC(df['high'],df['low'],df["close"])

    elif ind=="willr":
        result = talib.WILLR(df['high'],df['low'],df["close"])
        
    else:
        print("invalid indicator")
        return {}

    result = result.to_frame().reset_index()
    result.rename(columns = {0:'indicator_value'}, inplace = True)
    chart_data = {"Date":result["date_index"].tolist(),
                  "Indicator_value":result["indicator_value"].tolist()}
    return chart_data

    

@app.route('/technical_indicator_chart', methods=['GET'])
def technical_indicator_chart():
    ind = request.form.get('indicator')
    stock_name = request.form.get('stockName')
    candle_interval = request.form.get('candleInterval')
    if stock_name in stock_data:
        chart_data = technical_indicator(ind,stock_name,candle_interval)
        return chart_data
    else:
        print("invalid stock name")
        return {}


@app.route('/latest_technical_indicator', methods=['GET'])
def latest_technical_indicator():
    ind = request.form.get('indicator')
    stock_name = request.form.get('stockName')
    candle_interval = request.form.get('candleInterval')
    if stock_name in stock_data:
        chart_data = technical_indicator(ind,stock_name,candle_interval)
        latest_value = chart_data["Indicator_value"][-1]
        return {"latest_value": latest_value}
    else:
        print("invalid stock name")
        return {}


