## Sort and Map UAV Images
## (c) Andy Lyons, 2017

## Passed a directory containing geotagged images, this script will 
## i) Put the images into separate subfolders for each flight
## ii) Create a point shapefile of the centroids of each image

## Usage tips
## Be sure to double-quote around any directory names that contains spaces. E.g.,  
## python \GitHub\ParseDroneImgs\parse-uav-imgs.py 'C:\Temp\Thermal Dronnies'

## To run, open a command window and type:
## cd C:\GitHub\ParseDroneImgs
## python parse-uav-imgs.py 'C:\Pix4D\Elkus_Ranch\Data\20170419_Hero4\Flight01_1320_1321_120ft_WaterTower\Geotagged\GeotaggedWithExif'     #GoPro
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-16_X5\Flight02_1532_1540_400ft'             #X5 
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-17_Seq\Flight01_1321_1328_400ft\RGB'        #Sequoia RGB
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed1\Data\2017-01-17_Seq\Flight01_1321_1328_400ft\Multispec'  #Sequoia MSS 
## python parse-uav-imgs.py 'C:\Pix4D\HREC\HQ-Pasture\Data\HQPasture\201708017_X3b'  #X3
## python parse-uav-imgs.py 'C:\Pix4D\HREC\Watershed2\Data\2017-08-18_X3\Flight02_Imgs'
## python \GitHub\ParseDroneImgs\parse-uav-imgs.py "C:\Pix4D\Test\Test_SeqMixed"
## python \GitHub\ParseDroneImgs\parse-uav-imgs.py "C:\Pix4D\Test\Test_SeqRGB"

## Set default options
fnCSV = "exif_info.csv"
m2s_YN = False
m2s_ThreshUnits = "multiple of median sampling interval"    # or 'seconds'
m2s_ThreshVal = 10
m2s_Preview = True
m2s_MoveCopy = "move"
m2s_DivideTifJpgYN = False
m2s_SubDirJPG = "rgb"
m2s_SubDirTIF = "mss"
shpCreateYN = True
m2s_FirstFlightNum = 1
m2s_SubdirTemplate = "Flt{FltNum}_{StartTime}_{EndTime}"
shape_file_suffix = "_pts.shp"

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

## Create a function for colored text
def coltxt(strTxt, strCol="cyan", brightYN=True):
    dctANSI = {'black':Fore.BLACK, 'k':Fore.BLACK, 'red':Fore.RED, 'r':Fore.RED, 'green':Fore.GREEN, 'g':Fore.GREEN, 'yellow':Fore.YELLOW, 'y':Fore.YELLOW, 'blue':Fore.BLUE, 'b':Fore.BLUE, 'magenta':Fore.MAGENTA, 'm':Fore.MAGENTA, 'cyan':Fore.CYAN, 'c':Fore.CYAN, 'white':Fore.WHITE, 'w':Fore.WHITE, 'reset':Fore.RESET}
    if strCol in dctANSI.keys():
        return (Style.BRIGHT if brightYN else "") + dctANSI[strCol] + strTxt + Style.RESET_ALL
    else:
        print "color not found: " + strCol + Style.RESET_ALL
        return ""



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

## The first (and only) argument should be a path
fnInputDir = sys.argv[1]
fnInputDir = fnInputDir.strip('\'"')    # get rid of single and double quotes
fnInputLastDir = os.path.basename(os.path.normpath(fnInputDir))

## Make sure the directory exists
if not os.path.isdir(fnInputDir):
    print fnInputDir + " is not a directory."
    print "If launching from the command line, be sure to put double-quotes around directory names that conatain spaces."
    os.system("pause")
    quit()

## Define tags in the image header (these work with all cameras tested so far)
tagDateTimeOrig = "DateTimeOriginal"
tagLat = "GPSLatitude"
tagLong = "GPSLongitude"
tagsAllForCmd = "-" + tagDateTimeOrig + " -" + tagLat + " -" + tagLong

#tagsAllForCmd = tagsAllForCmd + " -filesize"

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
#strCmd = "exiftool -filename -gpsdatestamp -gpstimestamp -gpslatitude -gpslongitude -n -csv " + fnInputDir + " > " + fnCSV
#If useful could add -filesize# and other tags (like image size), Z value
strCmd = "exiftool -if \"$filesize# > 0\" -filename " + tagsAllForCmd + " -n -csv \"" + fnInputDir + "\" > \"" + fnCSV + "\""
#print strCmd

created_csv = call(strCmd, shell=True)
if created_csv != 0:
    print "Error extracting EXIF info (" + str(created_csv) + ")" 
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
    try:
        dtobj = datetime.strptime(row[tagDateTimeOrig], '%Y:%m:%d %H:%M:%S')
    except ValueError:
        print Style.BRIGHT + Fore.RED + row['FileName'] + " doesn't have a proper " + tagDateTimeOrig + " tag and will be excluded" + Style.RESET_ALL
    else:
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

            ## OLD: flights is a list containing the first and last index from file_dt, plus a constructed subdir name
            ## flights is a list containing lists with two elements: i) a list of indices from file_dt, and ii) constructed subdir name
            flights = []
            start_idx = 0
            cur_flight_num = 0
            for i in range(len(file_dt)):
                if i == (len(file_dt)-1) or timediffs[i] >= thresh_abs:
                    ## Add a flight - either the last one, or the one that just ended
                    end_idx = i-1 if timediffs[i] >= thresh_abs else i
                    subdir = m2s_SubdirTemplate                    
                    ## subdir = subdir.replace("{FltNum}", "%02d" % (len(flights) + m2s_FirstFlightNum))
                    subdir = subdir.replace("{FltNum}", "%02d" % (cur_flight_num + m2s_FirstFlightNum))
                    subdir = subdir.replace("{StartTime}", file_dt[start_idx][IDX_DTOBJ].strftime('%H%M'))
                    subdir = subdir.replace("{EndTime}", file_dt[end_idx][IDX_DTOBJ].strftime('%H%M'))
                    subdir = subdir.replace("{Date}", file_dt[end_idx][IDX_DTOBJ].strftime('%Y%m%d'))

                    if m2s_DivideTifJpgYN:
                        tif_idx = []
                        for j in range(start_idx, end_idx + 1):
                            if file_dt[j][0].lower().endswith(".tif"):
                                tif_idx.append(j)
                        if len(tif_idx) > 0:
                            flights.append([tif_idx, os.path.join(subdir, m2s_SubDirTIF)])
                        jpg_idx = []
                        for j in range(start_idx, end_idx + 1):
                            if file_dt[j][0].lower().endswith(".jpg"):
                                jpg_idx.append(j)
                        if len(jpg_idx) > 0:
                            flights.append([jpg_idx, os.path.join(subdir, m2s_SubDirJPG)])
                    else:
                        flights.append([range(start_idx, end_idx + 1), subdir])
                    cur_flight_num = cur_flight_num + 1
                    start_idx = i

                #elif timediffs[i] >= thresh_abs:
                    ## Start a new flight
                    #subdir = m2s_SubdirTemplate                    
                    #subdir = subdir.replace("{FltNum}", "%02d" % (len(flights) + m2s_FirstFlightNum))
                    #subdir = subdir.replace("{StartTime}", file_dt[start_idx][IDX_DTOBJ].strftime('%H%M'))
                    #subdir = subdir.replace("{EndTime}", file_dt[i-1][IDX_DTOBJ].strftime('%H%M'))
                    #subdir = subdir.replace("{Date}", file_dt[i][IDX_DTOBJ].strftime('%Y%m%d'))
                    #flights.append([start_idx, i-1, subdir])
                    #flights.append([range(start_idx, i), subdir])
                    #start_idx = i

        else:
            # Just one 'flight'
            #flights = [[0, len(file_dt)-1, "all"]]
            flights = [[range(len(file_dt)), "all"]]
        ComputeFlightGroupsYN = False

    ## Display menu
    print "\n---------------------------------------------"
    print "Input directory: " + coltxt(fnInputDir,"g")
    print "Num images found: " + coltxt(str(len(file_dt)),"g")
    print "Min, Median, and Max sampling interval (seconds): " + coltxt(str(min(timediffs[1:])) + ", " + str(median(timediffs)) + ", " + str(max(timediffs[1:])),"g")
    print "      -------------"
    print "Move files into sub-" + coltxt("D","c") + "irectories by flight: " + coltxt(str(m2s_YN),"g")
    if m2s_YN:
        print "Flight Parsing Options:"
        print "  Threshhold " + coltxt("U","c") + "nits: " + coltxt(m2s_ThreshUnits,"g")
        print "  Threshhold " + coltxt("V","c") + "al: " + coltxt(str(m2s_ThreshVal),"g")
        print "    --> will create a new flight every time a gap is found of at least " + str(thresh_abs) + " seconds"
        print "  Subdirectory name " + coltxt("T","c") + "emplate: " + m2s_SubdirTemplate
        print "  " + coltxt("F","c") + "irst flight number: " + coltxt(str(m2s_FirstFlightNum),"g")
        print "  Se" + coltxt("P","c") + "arate JPGs and TIFs: " + coltxt(str(m2s_DivideTifJpgYN),"g")
        print "  Flight directory(s):" 
        for i in range(len(flights)):
            print "   - " + coltxt(flights[i][1],"g") + " (" + str(len(flights[i][0])) + ")" 
        print "  " + coltxt("M","c") + "ove or " + coltxt("C","c") + "opy: " + coltxt(m2s_MoveCopy,"g")
    print "Create point " + coltxt("S","c") + "hapefiles: " + coltxt(str(shpCreateYN),"g")

    strPrompt = "Continue [y/n or d/u/v/f/m/c/p/s]? " if m2s_YN else "Continue [y/n or d/s]? "
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
    elif contYN.lower() == "p":
        m2s_DivideTifJpgYN = not m2s_DivideTifJpgYN
        ComputeFlightGroupsYN = True
    elif contYN.lower() == "t":
        print "The following pieces of the subdirectory name template will be replaced with actual values:"
        print "{FltNum}, {StartTime}, {EndTime}, {Date}"
        m2s_SubdirTemplate = raw_input("New subdirectory name template: ")
        #m2s_SubdirTemplate = raw_input("New subdirectory name template: %s" % m2s_SubdirTemplate + chr(8) * len(m2s_SubdirTemplate)) DOESNT WORK
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
        fnSubDir = flights[i][1]
        fnSubDirFullPath = os.path.join(fnInputDir, fnSubDir)
        #print "fnSubDirFullPath: " + fnSubDirFullPath
        if os.path.exists(fnSubDirFullPath):
            if overwrite_subdir != "a":
                print "Sub-directory " + fnSubDir + " already exists. Any files in it with the same name will be overwritten." 
                overwrite_subdir = raw_input("Continue [y/n/a]? ")
                overwrite_subdir = overwrite_subdir.lower()
                if overwrite_subdir != "y" and overwrite_subdir != "a":
                    quit()
        else:
            print "Creating subdirectory " + fnSubDir
            thisdir = fnInputDir
            for dirpart in fnSubDir.split(os.sep):
                thisdir = os.path.join(thisdir, dirpart)
                if not os.path.exists(thisdir):
                    print " - going to make the directory " + thisdir
                    os.mkdir(thisdir)

        if m2s_MoveCopy == "move":
            print "Moving files to " + fnSubDir + "..."
        elif m2s_MoveCopy == "copy":
            print "Copying files to " + fnSubDir + "..."

        #for j in range(flights[i][0], flights[i][1]+1):
        for j in flights[i][0]:
            fnSrc = os.path.join(fnInputDir, file_dt[j][IDX_FN])
            fnDest = os.path.join(fnSubDirFullPath, file_dt[j][IDX_FN])
            #print str(j) + ": " + fnSrc + " ==> " + fnDest
            print str(j) + ": " + os.path.basename(os.path.normpath(fnSrc)) + " ==> " + os.path.basename(os.path.normpath(fnDest))
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
            fnShp = os.path.join(fnInputDir, flight_info[1], (flight_info[1] + shape_file_suffix).replace(os.sep, "_"))  
        else:
            fnShp = os.path.join(fnInputDir, fnInputLastDir + shape_file_suffix)  
        #print "fnShp = " + fnShp
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
        #for i in range(flight_info[0], flight_info[1] + 1):
        for i in flight_info[0]:

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
print "  - rename script to uav-img-sort-and-map"
print "  - add a GUI"
print "  - option to project"
print "  - run it on multiple directories at once"
print "  - option to make a MCP"
print "  - option to recreate flight line"
print "  - give exif_info.csv a better name (based on the template for the shapefile), or first create it in Temp space and then rename"
print "  - additional option for where to save the shapefile (and what to name it)"
print "  - make the filename field in the attrbitute table a hotlink to the file (?)"
print "  - offer a couple of preset subdir name templates"
print "  - option to create a leaflet.js file, or load into ArcMap"
print "  - option to edit m2s_SubDirJPG and m2s_SubDirTIF"
print "  - add 'Make', 'Model', and elevation tags to shapefile attribute table"
print "  * specify which open source license this falls under"
print "  * add {date} as an option to the subdirectory naming template; offer a couple of preset templates"
print "  * add an option to sort jpgs and TIFF into separate folders"
print "  * test that the argument passed is an existing directory"
print "  * test what happens if input dir has spaces"
print "  * make a template for subfolder names, e.g., {date}_Flt{flight-num}_{flight-start-time}_{flight-end-time}_other-stuff"

##Pause the screen before closing (helpful when you run it from the 'Send To' menu)
os.system("pause")
