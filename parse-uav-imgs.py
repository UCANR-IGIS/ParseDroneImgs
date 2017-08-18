## Sort and Map UAV Images
## (c) Andy Lyons, 2017

## Passed a directory containing geotagged images, this script will 
## i) Put the images into separate subfolders for each flight
## ii) Create a point shapefile of the centroids of each image

## To run, open a command window and type:
## cd C:\GitHub\ParseDroneImgs
## python parse-uav-imgs.py 'C:\Pix4D\Elkus_Ranch\Data\20170419_Hero4\Flight01_1320_1321_120ft_WaterTower\Geotagged\GeotaggedWithExif'     #GoPro
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-16_X5\Flight02_1532_1540_400ft'             #X5 
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-17_Seq\Flight01_1321_1328_400ft\RGB'        #Sequoia RGB
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-17_Seq\Flight01_1321_1328_400ft\Multispec'  #Sequoia MSS 
## python parse-uav-imgs.py 'C:\Pix4D\HREC\HQ-Pasture\Data\HQPasture\201708017_X3b'  #X3

## Set default options
fnCSV = "exif_info.csv"
m2s_YN = False
m2s_ThreshUnits = "multiple of median sampling interval"    # or 'seconds'
m2s_ThreshVal = 10
m2s_Preview = True
m2s_MoveCopy = "move"
shpCreateYN = True
m2s_FirstFlightNum = 1
m2s_SubdirTemplate = "Flt{FltNum}_{StartTime}_{EndTime}"
shape_file_suffix = "pts.shp"

#Camera type no longer needed. The GoPro, X5, and Seq all share a set of tags
#camera_type = "GoPro"
#camera_type = "X5"
#If needed, the script could try to auto-detect the type of camera (and hence the EXIF tags used)
#ZenMuse X5 model: FC550

## Import modules
import os, sys
from subprocess import call
from datetime import datetime
from operator import itemgetter
from shutil import copyfile
import imp
from distutils import spawn

## Make sure a directory was passed
if len(sys.argv)==1:
    print "Please pass a directory name"
    os.system("pause")
    quit()

## Make sure exiftool is available
if spawn.find_executable("exiftool") is None:
    print "This script requires exiftool.exe to be somewhere on the system path"
    print "  a. Download it from http://www.sno.phy.queensu.ca/~phil/exiftool/"
    print "  b. Install"
    print "  c. Rename 'exiftool(-k).exe' to 'exiftool.exe'"
    print "  d. Move 'exiftool.exe' to a directory on the system PATH (like c:\windows)"
    os.system("pause")
    quit()

try:
    imp.find_module('colorama')
except ImportError:
    print "A required Python module colorama was not found."
    print "To install try:"
    print "cd C:\\Python27\\ArcGIS10.5\\Scripts"
    print "pip.exe install colorama"
    os.system("pause")
    quit()

from colorama import init, Fore, Back, Style
init()
#Fore: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
#Back: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET
#Style: DIM, NORMAL, BRIGHT, RESET_ALL (resets foreground, background, and brightness)

try:
    imp.find_module('osgeo')
    gdalYN = True
    import osgeo.ogr as ogr
    import osgeo.osr as osr
except ImportError:
    gdalYN = False
    print "python gdal module not found. Shapefile export will be disabled\n"

## Create a custom function we'll need later
def median(lst, omit_zeros=True):
    if omit_zeros:
        lst = [elem for elem in lst if elem != 0]
    n = len(lst)
    if n < 1:
        return None
    if n % 2 == 1:
        return sorted(lst)[n//2]
    else:
        return sum(sorted(lst)[n//2-1:n//2+1])/2.0

fnInputDir = sys.argv[1]
fnInputDir = fnInputDir.strip('\'"')    # get rid of single and double quotes

## Define tags in the image header (these work with all cameras tested so far)
tagDateTimeOrig = "DateTimeOriginal"
tagLat = "GPSLatitude"
tagLong = "GPSLongitude"
tagsAllForCmd = "-" + tagDateTimeOrig + " -" + tagLat + " -" + tagLong

## Not used (not needed for the cameras that have been tested)
#if camera_type == "GoPro" or camera_type == "X5":
#    tagDateTimeOrig = "DateTimeOriginal"
#    tagLat = "GPSLatitude"
#    tagLong = "GPSLongitude"
#    tagsAllForCmd = "-" + tagDateTimeOrig + " -" + tagLat + " -" + tagLong
#else:
#    print "Unknown camera type"
#    os.system("pause")
#    quit()

## Notes
## -filename is kind of redundant, the -n switch adds the filename and path
## GoPro Hero4 also has -GPSDateStamp -GPSTimeStamp (UTC time)

print "Running exiftool on images in " + fnInputDir + "..."
fnCSV = os.path.join(fnInputDir, fnCSV)
strCmd = "exiftool -filename " + tagsAllForCmd + " -n -csv " + fnInputDir + " > " + fnCSV

#strCmd = "exiftool -filename -gpsdatestamp -gpstimestamp -gpslatitude -gpslongitude -n -csv " + fnInputDir + " > " + fnCSV
#strCmd = "exiftool -filename " + tagsAllForCmd + " -n -csv " + fnInputDir + " > " + fnCSV

created_csv = call(strCmd, shell=True)
if created_csv != 0:
    print "Error extracting EXIF info"
    os.system("pause")
    quit()

### Use a dictionary reader on the csv file so we can access columns by field name
import csv
csvReader = csv.DictReader(open(fnCSV, "rb"), delimiter=',')   #, quoting=csv.QUOTE_NONE

### Check that all the field names are present
required_flds = [tagDateTimeOrig, tagLong, tagLat]
for fld in required_flds:
    if not fld in csvReader.fieldnames:
        print "Required tag not found: " + fld
        print "Make sure all the images in this folder have a DateTimeOriginal and geostamp tags"
        os.system("pause")
        quit()

### Input CSV data into a list of tuples
file_dt = []
for row in csvReader:
    # SourceFile, FileName, DateTimeOriginal, GPSLatitude, GPSLongitude
    dtobj = datetime.strptime(row[tagDateTimeOrig], '%Y:%m:%d %H:%M:%S')
    file_dt.append((row['FileName'], dtobj, row[tagLong], row[tagLat]))    #add a tuple

## Remember index locations within the tuple for later
IDX_FN = 0
IDX_DTOBJ = 1
IDX_LONG = 2
IDX_LAT = 3

## Sort file_dt based on datetime
file_dt.sort(key=itemgetter(IDX_DTOBJ))

## Compute the time interval between images
timezero = file_dt[0][1]
timediffs = [0]
for fdt in file_dt[1:]:
    this_offset = fdt[1] - timezero
    timediffs.append(this_offset.total_seconds())
    timezero = fdt[1]
#print "Time intervals (seconds): " + str(timediffs)

ShowMenuYN = True
ComputeFlightGroupsYN = True   ## compute flight groups first time through (at least)

while ShowMenuYN:
    if ComputeFlightGroupsYN:
        ## MAKE THE GROUPS
        if m2s_YN:
            ## Compute the absolute time threshhold (gap) in seconds
            if m2s_ThreshUnits == "multiple of median sampling interval":
                thresh_abs = m2s_ThreshVal * median(timediffs)
            else:
                thresh_abs = m2s_ThreshVal

            ## flights is a list containing the first and last index from file_dt, plus a constructed subdir name
            flights = []
            start_idx = 0
            for i in range(len(file_dt)):
                if i == (len(file_dt)-1):
                    #subdir = "Flt" +  "%02d" % (len(flights) + m2s_FirstFlightNum) + "_" + file_dt[start_idx][IDX_DTOBJ].strftime('%H%M') + "_" + file_dt[i][IDX_DTOBJ].strftime('%H%M')
                    subdir = m2s_SubdirTemplate                    
                    subdir = subdir.replace("{FltNum}", "%02d" % (len(flights) + m2s_FirstFlightNum))
                    subdir = subdir.replace("{StartTime}", file_dt[start_idx][IDX_DTOBJ].strftime('%H%M'))
                    subdir = subdir.replace("{EndTime}", file_dt[i][IDX_DTOBJ].strftime('%H%M'))
                    flights.append([start_idx, i, subdir])
                elif timediffs[i] >= thresh_abs:
                    ## Start a new flight
                    #subdir = "Flt" +  "%02d" % (len(flights) + m2s_FirstFlightNum) + "_" + file_dt[start_idx][IDX_DTOBJ].strftime('%H%M') + "_" + file_dt[i-1][IDX_DTOBJ].strftime('%H%M')
                    subdir = m2s_SubdirTemplate                    
                    subdir = subdir.replace("{FltNum}", "%02d" % (len(flights) + m2s_FirstFlightNum))
                    subdir = subdir.replace("{StartTime}", file_dt[start_idx][IDX_DTOBJ].strftime('%H%M'))
                    subdir = subdir.replace("{EndTime}", file_dt[i-1][IDX_DTOBJ].strftime('%H%M'))
                    flights.append([start_idx, i-1, subdir])
                    start_idx = i
        else:
            # Just one 'flight'
            flights = [[0, len(file_dt)-1, "all"]]
        ComputeFlightGroupsYN = False

    ## Display menu
    print "\nNum images found: " + str(len(file_dt)) 
    print "Min, Median, and Max sampling interval (seconds): " + Style.BRIGHT + Fore.GREEN + str(min(timediffs[1:])) + ", " + str(median(timediffs)) + ", " + str(max(timediffs[1:])) + Style.RESET_ALL
    print "Move files into sub-" + Style.BRIGHT + Fore.CYAN + "D" + Style.RESET_ALL + "irectories by flight: " + Style.BRIGHT + Fore.GREEN + str(m2s_YN) + Style.RESET_ALL
    if m2s_YN:
        print "Flight Parsing Options:"
        print "  Threshhold " + Style.BRIGHT + Fore.CYAN + "U" + Style.RESET_ALL + "nits: " + Style.BRIGHT + Fore.GREEN + m2s_ThreshUnits + Style.RESET_ALL
        print "  Threshhold " + Style.BRIGHT + Fore.CYAN + "V" + Style.RESET_ALL + "al: " + Style.BRIGHT + Fore.GREEN + str(m2s_ThreshVal) + Style.RESET_ALL
        print "    --> will create a new flight every time a gap is found of at least " + str(thresh_abs) + " seconds"
        print "  Subdirectory name " + Style.BRIGHT + Fore.CYAN + "T" + Style.RESET_ALL + "emplate: " + m2s_SubdirTemplate
        print "  " + Style.BRIGHT + Fore.CYAN + "F" + Style.RESET_ALL + "irst flight number: " + str(m2s_FirstFlightNum)
        print "  Flight directory(s):" 
        for i in range(len(flights)):
            print "   - " + flights[i][2]  
            #print "   - Flt" +  "%02d" % (i + m2s_FirstFlightNum) + ": " + file_dt[flights[i][0]][IDX_DTOBJ].strftime('%H:%M:%S') + " to " + file_dt[flights[i][1]][IDX_DTOBJ].strftime('%H:%M:%S') + " (" + str(flights[i][1] - flights[i][0] + 1) + " images)"
        print "  " + Style.BRIGHT + Fore.CYAN + "M" + Style.RESET_ALL + "ove or " + Style.BRIGHT + Fore.CYAN + "c" + Style.RESET_ALL + "opy: " + Style.BRIGHT + Fore.GREEN + m2s_MoveCopy + Style.RESET_ALL
    print "Create point " + Style.BRIGHT + Fore.CYAN + "S" + Style.RESET_ALL + "hapefiles: " + Style.BRIGHT + Fore.GREEN + str(shpCreateYN) + Style.RESET_ALL

    strPrompt = "Continue [y/n or d/u/v/f/m/c/s]? " if m2s_YN else "Continue [y/n or d/s]? "
    contYN = raw_input(strPrompt)
    if contYN.lower() == "y": 
        ShowMenuYN = False
    elif contYN.lower() == "d":
        m2s_YN = not m2s_YN
        ComputeFlightGroupsYN = True
    elif contYN.lower() == "u":
        m2s_ThreshUnits = "multiple of median sampling interval" if m2s_ThreshUnits == 'seconds' else 'seconds'
        ComputeFlightGroupsYN = True
    elif contYN.lower() == "c":
        m2s_MoveCopy = "copy"
    elif contYN.lower() == "m":
        m2s_MoveCopy = "move"
    elif contYN.lower() == "s":
        shpCreateYN = not shpCreateYN
    elif contYN.lower() == "t":
        print "The following pieces of the subdirectory name template will be replaced with actual values:"
        print "{FltNum}, {StartTime}, {EndTime}"
        m2s_SubdirTemplate = raw_input("New subdirectory name template: ")
        ComputeFlightGroupsYN = True
    elif contYN.lower() == "f":
        m2s_FirstFlightNum = int(raw_input("First flight number: "))
        ComputeFlightGroupsYN = True
    elif contYN.lower() == "v":
        m2s_ThreshVal = int(raw_input("Threshhold value: "))
        ComputeFlightGroupsYN = True
    else:
        quit()

## Create subdirectories and move files
if m2s_YN:
    overwrite_subdir = "u"
    for i in range(len(flights)):
        #fnSubDir = "Flt" +  "%02d" % (i + m2s_FirstFlightNum) + "_" + file_dt[flights[i][0]][IDX_DTOBJ].strftime('%H%M') + "_" + file_dt[flights[i][1]][IDX_DTOBJ].strftime('%H%M')        
        fnSubDir = flights[i][2]
        fnSubDirFullPath = os.path.join(fnInputDir, fnSubDir)
        ##print fnSubDirFullPath + " exists: " + str(os.path.exists(fnSubDirFullPath))
        if os.path.exists(fnSubDirFullPath):
            if overwrite_subdir != "a":
                print "Sub-directory " + fnSubDir + " already exists. Any files in it with the same name will be overwritten." 
                overwrite_subdir = raw_input("Continue [y/n/a]? ")
                overwrite_subdir = overwrite_subdir.lower()
                if overwrite_subdir != "y" and overwrite_subdir != "a":
                    quit()
        else:
            print "Creating subdirectory " + fnSubDir
            os.mkdir(fnSubDirFullPath)

        if m2s_MoveCopy == "move":
            print "Moving files to " + fnSubDir + "..."
        elif m2s_MoveCopy == "copy":
            print "Copying files to " + fnSubDir + "..."

        for j in range(flights[i][0], flights[i][1]+1):
            fnSrc = os.path.join(fnInputDir, file_dt[j][IDX_FN])
            fnDest = os.path.join(fnSubDirFullPath, file_dt[j][IDX_FN])
            #print str(j) + ": " + fnSrc + " ==> " + fnDest
            if m2s_MoveCopy == "move":
                os.rename(fnSrc, fnDest)
            elif m2s_MoveCopy == "copy":
                copyfile(fnSrc, fnDest)

## CREATE POINT SHAPEFILE OF IMAGE CENTROIDS
if gdalYN and shpCreateYN:
    print "Exporting image centroids"

    # Set up the shapefile driver
    driver = ogr.GetDriverByName("ESRI Shapefile")

    for flight_info in flights:  

        # Create the data source
        if m2s_YN:
            fnShp = os.path.join(fnInputDir, flight_info[2], flight_info[2] + "_" + shape_file_suffix)  
        else:
            fnShp = os.path.join(fnInputDir, shape_file_suffix)  
        data_source = driver.CreateDataSource(fnShp)

        # Create the spatial reference, WGS84
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)

        # Create the layer
        layer = data_source.CreateLayer("Img", srs, ogr.wkbPoint)

        # Add fields
        fldFn = ogr.FieldDefn("fn", ogr.OFTString)
        fldFn.SetWidth(254)
        layer.CreateField(fldFn)

        fldDate = ogr.FieldDefn("date", ogr.OFTString)
        fldDate.SetWidth(10)
        layer.CreateField(fldDate)

        fldTime = ogr.FieldDefn("time", ogr.OFTString)
        fldTime.SetWidth(10)
        layer.CreateField(fldTime)

        layer.CreateField(ogr.FieldDefn("Latitude", ogr.OFTReal))
        layer.CreateField(ogr.FieldDefn("Longitude", ogr.OFTReal))

        ## Add records
        for i in range(flight_info[0], flight_info[1] + 1):

            # create the feature
            feature = ogr.Feature(layer.GetLayerDefn())

            # Set the attributes using the values from file_dt
            feature.SetField("fn", file_dt[i][IDX_FN])
            feature.SetField("date", file_dt[i][IDX_DTOBJ].strftime('%Y:%m:%d'))
            feature.SetField("time", file_dt[i][IDX_DTOBJ].strftime('%H:%M:%S'))
            feature.SetField("latitude", file_dt[i][IDX_LAT])
            feature.SetField("longitude", file_dt[i][IDX_LONG])

            # create the WKT for the feature using Python string formatting
            wkt = "POINT(%f %f)" %  (float(file_dt[i][IDX_LONG]) , float(file_dt[i][IDX_LAT]))

            # Create the point from the Well Known Txt
            point = ogr.CreateGeometryFromWkt(wkt)

            # Set the feature geometry using the point
            feature.SetGeometry(point)

            # Create the feature in the layer (shapefile)
            layer.CreateFeature(feature)

            # Dereference the feature
            feature = None

        # Save and close the data source
        data_source = None

        print "Created " + fnShp

print Style.BRIGHT + Fore.YELLOW + "Done" + Style.RESET_ALL

print "\nStill to come:"
print "  - make the filename field in the attrbitute table a hotlink to the file (?)"
print "  - consider adding 'Make' and 'Model' tags to shapefile attribute table"
print "  - test that the argument passed is an existing directory"
print "  - test what happens if input dir has spaces"
print "  * make a template for subfolder names, e.g., {date}_Flt{flight-num}_{flight-start-time}_{flight-end-time}_other-stuff"

##Pause the screen before closing (helpful when you run it from the 'Send To' menu)
os.system("pause")
