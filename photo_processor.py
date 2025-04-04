"""
Photo Appendix Generator - Photo Processing Module
This module handles reading photos and extracting metadata.
"""
import os
import exifread
from PIL import Image
import re
import tempfile
import shutil
import subprocess
import json
from datetime import datetime
from fractions import Fraction

# Try to import pillow_heif for HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False
    print("Warning: pillow-heif not installed. HEIC support limited.")

def get_heic_metadata_with_exiftool(photo_path):
    """
    Use ExifTool to extract metadata from HEIC files (more reliable).
    
    Args:
        photo_path (str): Path to the photo file
        
    Returns:
        dict: Dictionary containing metadata from ExifTool
    """
    try:
        # Check if exiftool is installed
        if os.name == 'nt':  # Windows
            exiftool_cmd = 'exiftool'
            check_cmd = ['where', 'exiftool']
        else:  # macOS/Linux
            exiftool_cmd = 'exiftool'
            check_cmd = ['which', 'exiftool']
            
        try:
            result = subprocess.run(check_cmd, 
                                capture_output=True, 
                                text=True, 
                                check=False)
            
            if result.returncode != 0:
                print(f"Warning: ExifTool not found. Install with 'brew install exiftool' (Mac) or download from https://exiftool.org (Windows)")
                print("Attempting to use ExifTool anyway...")
        except Exception as e:
            print(f"Error checking for ExifTool: {str(e)}")
            print("Continuing anyway...")
            
        # Run exiftool with JSON output format and GPS coordinates
        print(f"Running ExifTool on {photo_path}")
        cmd = [exiftool_cmd, '-j', '-n', '-a', '-u', '-G1', photo_path]
        print(f"ExifTool command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0 and result.stdout:
            # Parse JSON output
            try:
                metadata = json.loads(result.stdout)
                if metadata and isinstance(metadata, list) and len(metadata) > 0:
                    return metadata[0]  # Return the first item (should be only one)
                return {}
            except json.JSONDecodeError:
                print(f"Error parsing ExifTool JSON output: {result.stdout[:100]}...")
                return {}
        else:
            print(f"ExifTool error: {result.stderr}")
            print(f"ExifTool output: {result.stdout[:100]}...")
            return {}
    except Exception as e:
        print(f"Error using ExifTool: {str(e)}")
        return {}

def debug_heic_with_exiftool(photo_path):
    """
    Print all metadata found by ExifTool for debugging.
    
    Args:
        photo_path (str): Path to the photo file
        
    Returns:
        dict: Dictionary containing description-related fields
    """
    metadata = get_heic_metadata_with_exiftool(photo_path)
    print(f"\n===== EXIFTOOL DEBUG FOR {os.path.basename(photo_path)} =====")
    print(json.dumps(metadata, indent=2))
    print("=== END EXIFTOOL DEBUG ===\n")
    
    # Return any description-like fields
    description_fields = {}
    for key, value in metadata.items():
        if any(term in key.lower() for term in ['descr', 'caption', 'title', 'comment']):
            description_fields[key] = value
    return description_fields

def extract_all_metadata(photo_path):
    """
    Extract and print all metadata from a photo for debugging purposes.
    """
    try:
        print(f"\n===== METADATA DEBUG FOR {os.path.basename(photo_path)} =====")
        
        # Check if it's a HEIC file
        is_heic = photo_path.lower().endswith('.heic')
        
        # For HEIC files, try ExifTool first
        description_tags = []
        if is_heic:
            print("Using ExifTool for HEIC file metadata")
            exiftool_metadata = get_heic_metadata_with_exiftool(photo_path)
            if exiftool_metadata:
                # Look for description-like fields
                for key, value in exiftool_metadata.items():
                    if any(keyword in key.lower() for keyword in ['descr', 'comment', 'caption', 'title', 'subject']):
                        if value and str(value).strip():
                            description_tags.append((key, str(value)))
                            print(f"  Potential caption tag from ExifTool: {key} = {value}")
            else:
                print("No metadata found with ExifTool")

        # For HEIC files, skip exifread which often raises hdlr errors
        if not is_heic:
            # Try exifread for non-HEIC files
            try:
                with open(photo_path, 'rb') as f:
                    tags = exifread.process_file(f, details=True)
                
                print(f"EXIF Tags found: {len(tags)}")
                
                # Print all tags containing description, comment, caption, title or subject
                for tag_name, value in tags.items():
                    keywords = ['descr', 'comment', 'caption', 'title', 'subject']
                    if any(keyword in tag_name.lower() for keyword in keywords):
                        description_tags.append((tag_name, str(value)))
                        print(f"  Potential caption tag: {tag_name} = {value}")
            except Exception as specific_error:
                print(f"Error reading EXIF data: {str(specific_error)}")
        else:
            print("Skipping exifread for HEIC file to avoid hdlr errors")
        
        # If on macOS, try mdls command first (more reliable for Apple formats)
        if os.path.exists('/usr/bin/mdls'):
            try:
                # Try the specific description field first
                result = subprocess.run(
                    ['/usr/bin/mdls', '-name', 'kMDItemDescription', photo_path], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                if result.returncode == 0 and result.stdout:
                    output = result.stdout.strip()
                    print(f"mdls description: {output}")
                    
                    if "kMDItemDescription" in output and "(null)" not in output:
                        match = re.search(r'"([^"]+)"', output)
                        if match:
                            description = match.group(1)
                            description_tags.append(('mdls:kMDItemDescription', description))
                            print(f"  Found description in mdls: {description}")
                
                # Try all metadata
                keywords = ['descr', 'comment', 'caption', 'title', 'subject']
                result = subprocess.run(
                    ['/usr/bin/mdls', photo_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    print("MDLS Metadata Output:")
                    for line in result.stdout.split('\n'):
                        if any(keyword in line.lower() for keyword in keywords):
                            print(f"  {line.strip()}")
                            # Try to extract the value
                            match = re.search(r'= "(.*?)"', line)
                            if match and match.group(1) != "(null)":
                                key = line.split('=')[0].strip()
                                description_tags.append((f'mdls:{key}', match.group(1)))
            except Exception as e:
                print(f"Error running mdls: {str(e)}")
        
        # If on macOS, try sips command as well
        if os.path.exists('/usr/bin/sips'):
            try:
                result = subprocess.run(
                    ['/usr/bin/sips', '-j', 'metadata', photo_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    print("SIPS Metadata Output:")
                    for line in result.stdout.split('\n'):
                        keywords = ['descr', 'comment', 'caption', 'title', 'subject']
                        if any(keyword in line.lower() for keyword in keywords):
                            print(f"  {line.strip()}")
                            # Try to extract the description value
                            match = re.search(r'"([^"]+)"\s*:\s*"([^"]+)"', line)
                            if match:
                                key, value = match.groups()
                                description_tags.append((f'sips:{key}', value))
            except Exception as e:
                print(f"Error running sips: {str(e)}")
        
        print("=== END METADATA DEBUG ===\n")
        return description_tags
        
    except Exception as e:
        print(f"Error during metadata debugging: {str(e)}")
        return []

def convert_gps_to_decimal(gps_coords, gps_ref):
    """
    Convert GPS coordinates from degrees/minutes/seconds to decimal degrees.
    
    Args:
        gps_coords: GPS coordinates in [degrees, minutes, seconds] format
        gps_ref: Reference direction (N/S/E/W)
        
    Returns:
        float: GPS coordinates in decimal degrees
    """
    try:
        # Handle various formats
        if isinstance(gps_coords, list) and len(gps_coords) == 3:
            degrees = float(gps_coords[0])
            minutes = float(gps_coords[1])
            seconds = float(gps_coords[2])
            
            decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        elif isinstance(gps_coords, str):
            # Try to parse string like "51 deg 30' 15.4\" N"
            gps_coords = gps_coords.replace('deg', '').replace("'", '').replace('"', '').strip()
            parts = gps_coords.split()
            
            if len(parts) >= 1:
                degrees = float(parts[0])
                minutes = float(parts[1]) if len(parts) > 1 else 0
                seconds = float(parts[2]) if len(parts) > 2 else 0
                
                decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
            else:
                # Try to parse as a simple float
                decimal = float(gps_coords)
        elif isinstance(gps_coords, (int, float)):
            # Already a decimal
            decimal = float(gps_coords)
        else:
            print(f"Unknown GPS format: {type(gps_coords)}, {gps_coords}")
            return None
        
        # If reference is South or West, negate the coordinate
        if gps_ref in ['S', 'W']:
            decimal = -decimal
            
        return decimal
    except Exception as e:
        print(f"Error converting GPS coordinates: {str(e)}")
        return None

def extract_gps_data(tags=None, exiftool_metadata=None, file_path=None):
    """
    Extract GPS data from EXIF tags or ExifTool metadata.
    
    Args:
        tags: EXIF tags from exifread
        exiftool_metadata: Metadata from ExifTool for HEIC files
        file_path: Path to the photo file (for debug output)
        
    Returns:
        tuple: (latitude, longitude) in decimal degrees or (None, None) if not available
    """
    latitude, longitude = None, None
    file_name = os.path.basename(file_path) if file_path else "unknown"
    
    print(f"Extracting GPS data for {file_name}")
    
    # First try ExifTool metadata if available (more reliable for all files)
    if exiftool_metadata:
        print("Attempting to extract GPS from ExifTool metadata")
        
        # Look for GPS in a variety of standard tags
        gps_keys = [
            # Common ExifTool GPS tags
            ('EXIF:GPSLatitude', 'EXIF:GPSLatitudeRef', 'EXIF:GPSLongitude', 'EXIF:GPSLongitudeRef'),
            ('Composite:GPSLatitude', 'Composite:GPSLatitudeRef', 'Composite:GPSLongitude', 'Composite:GPSLongitudeRef'),
            ('XMP:GPSLatitude', 'XMP:GPSLatitudeRef', 'XMP:GPSLongitude', 'XMP:GPSLongitudeRef'),
            ('GPS:Latitude', 'GPS:LatitudeRef', 'GPS:Longitude', 'GPS:LongitudeRef'),
            # Check for iOS/Apple specific formats
            ('EXIF:GPSLatitude', None, 'EXIF:GPSLongitude', None),
            ('Composite:GPSPosition', None, None, None)
        ]
        
        # Try each set of keys
        for lat_key, lat_ref_key, lon_key, lon_ref_key in gps_keys:
            try:
                # Handle composite GPS Position (format: "lat, lon")
                if lat_key == 'Composite:GPSPosition' and lat_key in exiftool_metadata:
                    position = exiftool_metadata[lat_key]
                    print(f"Found Composite GPS Position: {position}")
                    if isinstance(position, str) and ',' in position:
                        lat_str, lon_str = position.split(',')
                        latitude = float(lat_str.strip())
                        longitude = float(lon_str.strip())
                        print(f"Parsed GPS Position: Lat {latitude}, Lon {longitude}")
                        break
                        
                # Handle regular lat/lon pairs
                elif lat_key in exiftool_metadata and lon_key in exiftool_metadata:
                    lat = exiftool_metadata[lat_key]
                    lon = exiftool_metadata[lon_key]
                    
                    # Get reference directions if available
                    lat_ref = exiftool_metadata.get(lat_ref_key, 'N') if lat_ref_key else 'N'
                    lon_ref = exiftool_metadata.get(lon_ref_key, 'E') if lon_ref_key else 'E'
                    
                    # If latitude or longitude are already negative, no need for reference
                    if isinstance(lat, (int, float)) and lat < 0:
                        lat_ref = None
                    if isinstance(lon, (int, float)) and lon < 0:
                        lon_ref = None
                        
                    print(f"Found GPS data - Lat: {lat} {lat_ref}, Lon: {lon} {lon_ref}")
                    
                    # Convert to decimal format if needed
                    latitude = convert_gps_to_decimal(lat, lat_ref) if lat_ref else float(lat)
                    longitude = convert_gps_to_decimal(lon, lon_ref) if lon_ref else float(lon)
                    
                    print(f"Converted to decimal - Lat: {latitude}, Lon: {longitude}")
                    break
            except Exception as e:
                print(f"Error extracting GPS from keys {lat_key}/{lon_key}: {str(e)}")
                continue
                
        # If we still don't have GPS, search for any keys that might contain GPS data
        if latitude is None or longitude is None:
            print("Searching for any GPS-related keys in ExifTool metadata")
            for key, value in exiftool_metadata.items():
                if 'gps' in key.lower() or 'latitude' in key.lower() or 'longitude' in key.lower():
                    print(f"Potential GPS key: {key} = {value}")
    
    # If not found in ExifTool data, try exifread tags
    if (latitude is None or longitude is None) and tags:
        print("Attempting to extract GPS from EXIF tags")
        try:
            # Check if GPS data exists
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                # Get latitude information
                lat = tags['GPS GPSLatitude'].values
                lat_ref = tags.get('GPS GPSLatitudeRef', 'N').values
                
                # Get longitude information
                lon = tags['GPS GPSLongitude'].values
                lon_ref = tags.get('GPS GPSLongitudeRef', 'E').values
                
                print(f"Found GPS in EXIF - Lat: {lat} {lat_ref}, Lon: {lon} {lon_ref}")
                
                # Convert to decimal degrees
                latitude = convert_gps_to_decimal(lat, lat_ref)
                longitude = convert_gps_to_decimal(lon, lon_ref)
                
                print(f"Converted to decimal - Lat: {latitude}, Lon: {longitude}")
        except Exception as e:
            print(f"Error extracting GPS from EXIF: {str(e)}")
    
    # If still not found but on macOS, try mdls command
    if (latitude is None or longitude is None) and os.path.exists('/usr/bin/mdls'):
        print("Attempting to extract GPS from macOS mdls")
        try:
            # Check for GPS data with mdls (macOS)
            lat_cmd = ['/usr/bin/mdls', '-name', 'kMDItemLatitude', file_path]
            lon_cmd = ['/usr/bin/mdls', '-name', 'kMDItemLongitude', file_path]
            
            lat_result = subprocess.run(lat_cmd, capture_output=True, text=True, check=False)
            lon_result = subprocess.run(lon_cmd, capture_output=True, text=True, check=False)
            
            if lat_result.returncode == 0 and lon_result.returncode == 0:
                lat_output = lat_result.stdout.strip()
                lon_output = lon_result.stdout.strip()
                
                print(f"mdls latitude output: {lat_output}")
                print(f"mdls longitude output: {lon_output}")
                
                # Extract numeric values (if present)
                lat_match = re.search(r'= ([-\d.]+)', lat_output)
                lon_match = re.search(r'= ([-\d.]+)', lon_output)
                
                if lat_match and lon_match:
                    latitude = float(lat_match.group(1))
                    longitude = float(lon_match.group(1))
                    print(f"Found GPS in mdls - Lat: {latitude}, Lon: {longitude}")
        except Exception as e:
            print(f"Error extracting GPS from mdls: {str(e)}")
    
    # Try one more direct ExifTool command specifically for GPS
    if (latitude is None or longitude is None) and file_path:
        print("Trying direct ExifTool GPS extraction")
        try:
            if os.name == 'nt':  # Windows
                exiftool_cmd = 'exiftool'
            else:  # macOS/Linux
                exiftool_cmd = 'exiftool'
                
            # Simple command to extract just GPS
            cmd = [exiftool_cmd, '-n', '-json', '-GPSLatitude', '-GPSLongitude', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0 and result.stdout:
                try:
                    gps_data = json.loads(result.stdout)
                    if gps_data and isinstance(gps_data, list) and len(gps_data) > 0:
                        gps_data = gps_data[0]
                        if 'GPSLatitude' in gps_data and 'GPSLongitude' in gps_data:
                            latitude = float(gps_data['GPSLatitude'])
                            longitude = float(gps_data['GPSLongitude'])
                            print(f"Found GPS with direct ExifTool - Lat: {latitude}, Lon: {longitude}")
                except json.JSONDecodeError:
                    print(f"Error parsing direct ExifTool JSON: {result.stdout[:100]}...")
        except Exception as e:
            print(f"Error with direct ExifTool GPS extraction: {str(e)}")
    
    # Final validation of coordinates
    if latitude is not None and longitude is not None:
        # Check if coordinates are in valid ranges
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            print(f"Valid GPS coordinates found - Lat: {latitude}, Lon: {longitude}")
            return latitude, longitude
        else:
            print(f"Invalid GPS coordinates - Lat: {latitude}, Lon: {longitude}")
            return None, None
    else:
        print("No GPS coordinates found")
        return None, None

def extract_orientation_data(tags, exiftool_metadata=None):
    """
    Extract compass orientation data from EXIF tags or ExifTool metadata.
    
    Args:
        tags: EXIF tags from exifread
        exiftool_metadata: Metadata from ExifTool for HEIC files
        
    Returns:
        float: Direction in degrees (0-360) or None if not available
    """
    orientation = None
    
    # First try ExifTool metadata if available
    if exiftool_metadata:
        # Check various fields that might contain orientation
        orientation_fields = [
            'EXIF:GPSImgDirection',
            'XMP:GPSImgDirection',
            'GPS:GPSImgDirection',
            'GPS:ImgDirection',
            'EXIF:GPSDestBearing',
            'XMP:GPSDestBearing'
        ]
        
        for field in orientation_fields:
            if field in exiftool_metadata and exiftool_metadata[field] is not None:
                try:
                    orientation = float(exiftool_metadata[field])
                    print(f"Found orientation in ExifTool {field}: {orientation}")
                    break
                except (ValueError, TypeError):
                    continue
    
    # If not found in ExifTool data, try exifread tags
    if orientation is None and tags:
        orientation_tags = [
            'GPS GPSImgDirection',
            'GPS GPSDestBearing'
        ]
        
        for tag in orientation_tags:
            if tag in tags:
                try:
                    # Get the value (could be a fraction)
                    value = tags[tag].values[0]
                    
                    # Convert to float
                    if isinstance(value, Fraction):
                        orientation = float(value)
                    else:
                        orientation = float(value)
                        
                    print(f"Found orientation in EXIF {tag}: {orientation}")
                    break
                except (ValueError, TypeError, IndexError):
                    continue
    
    return orientation

def extract_metadata_from_photo(photo_path):
    """
    Extract metadata from a single photo.
    
    Args:
        photo_path (str): Path to the photo file
        
    Returns:
        dict: Dictionary containing photo data and metadata
    """
    photo_data = {
        'path': photo_path,
        'filename': os.path.basename(photo_path),
        'caption': None,
        'temp_file': None  # Will store path to temp converted file if needed
    }
    
    # Check if it's a HEIC file
    is_heic = photo_path.lower().endswith('.heic')
    
    # For HEIC files, try ExifTool first (most reliable)
    if is_heic:
        exiftool_metadata = get_heic_metadata_with_exiftool(photo_path)
        
        # Check several common description fields
        description_fields = [
            'EXIF:ImageDescription',
            'XMP:Description', 
            'XMP:Title',
            'XMP:Headline',
            'XMP:Caption',
            'XMP:CaptionWriter',
            'IPTC:Caption-Abstract',
            'IPTC:Headline',
            'QuickTime:Title',
            'QuickTime:Description',
            'Apple:Description'
        ]
        
        for field in description_fields:
            if field in exiftool_metadata and exiftool_metadata[field]:
                photo_data['caption'] = exiftool_metadata[field]
                print(f"Found caption in ExifTool {field}: {photo_data['caption']}")
                break
    
    # If no caption found via ExifTool or not a HEIC file, proceed with existing methods
    if not photo_data['caption']:
        # Run detailed metadata extraction for debugging
        description_tags = extract_all_metadata(photo_path)
        
        try:
            # For HEIC files, we may need to convert them for dimension extraction
            if is_heic:
                try:
                    # First try opening with pillow_heif if available
                    with Image.open(photo_path) as img:
                        photo_data['width'], photo_data['height'] = img.size
                        
                        # Create a temporary JPEG file that other libraries can work with
                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                        temp_file.close()
                        
                        # Convert HEIC to JPEG
                        img.convert('RGB').save(temp_file.name, 'JPEG')
                        photo_data['temp_file'] = temp_file.name
                        
                        # Use the converted file for further processing
                        converted_path = temp_file.name
                except Exception as e:
                    print(f"Error converting HEIC file {photo_path}: {str(e)}")
                    # Set converted_path to original in case of failure
                    converted_path = photo_path
            else:
                # For non-HEIC files, use the original path
                converted_path = photo_path
                
                # Get image dimensions
                with Image.open(photo_path) as img:
                    photo_data['width'], photo_data['height'] = img.size
            
            # Try to extract metadata from the file using exifread
            if not is_heic:  # Skip exifread for HEIC files to avoid hdlr errors
                try:
                    with open(converted_path, 'rb') as f:
                        tags = exifread.process_file(f, details=False)
                        
                    # If we found description tags during debugging, use them first
                    if description_tags:
                        for tag_name, value in description_tags:
                            if value and value.strip():
                                photo_data['caption'] = value.strip()
                                print(f"Using caption from {tag_name}: {photo_data['caption']}")
                                break
                    
                    # If no caption found yet, check standard EXIF tags
                    if not photo_data['caption']:
                        # Extract caption (could be in different EXIF tags depending on the source)
                        caption_tags = [
                            'Image ImageDescription', 
                            'EXIF UserComment',
                            'XMP:Description',
                            'IPTC:Caption-Abstract',
                            'EXIF:ImageDescription',
                            'EXIF:UserComment',
                            'EXIF:XPComment',
                            'EXIF:XPSubject',
                            'EXIF:XPTitle',
                            'EXIF:Description',
                            'EXIF:Subject'
                        ]
                        
                        # Try to find a caption in the available tags
                        for tag in caption_tags:
                            if tag in tags:
                                # Clean up the caption - remove unnecessary prefixes/chars
                                caption = str(tags[tag]).strip()
                                if caption:
                                    photo_data['caption'] = caption
                                    print(f"Found caption in {tag}: {caption}")
                                    break
                except Exception as e:
                    print(f"Error reading EXIF data: {str(e)}")
            else:
                # For HEIC files, use description_tags from debugging
                if description_tags:
                    for tag_name, value in description_tags:
                        if value and value.strip():
                            photo_data['caption'] = value.strip()
                            print(f"Using caption from {tag_name}: {photo_data['caption']}")
                            break
            
            # For macOS, prioritize mdls command for metadata extraction (works better with HEIC)
            if not photo_data['caption'] and os.path.exists('/usr/bin/mdls'):
                try:
                    # First try to get the specific description field
                    result = subprocess.run(
                        ['/usr/bin/mdls', '-name', 'kMDItemDescription', photo_path], 
                        capture_output=True, 
                        text=True, 
                        check=False
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        # Parse the output
                        output = result.stdout.strip()
                        if "kMDItemDescription" in output and "(null)" not in output:
                            # Extract the description value
                            match = re.search(r'"([^"]+)"', output)
                            if match:
                                photo_data['caption'] = match.group(1)
                                print(f"Found caption in mdls output: {photo_data['caption']}")
                    
                    # If still no caption, try other metadata fields
                    if not photo_data['caption']:
                        # Try common caption fields
                        caption_fields = [
                            'kMDItemTitle',
                            'kMDItemSubject',
                            'kMDItemComment',
                            'kMDItemHeadline'
                        ]
                        
                        for field in caption_fields:
                            result = subprocess.run(
                                ['/usr/bin/mdls', '-name', field, photo_path], 
                                capture_output=True, 
                                text=True, 
                                check=False
                            )
                            
                            if result.returncode == 0 and result.stdout:
                                output = result.stdout.strip()
                                if field in output and "(null)" not in output:
                                    match = re.search(r'"([^"]+)"', output)
                                    if match:
                                        photo_data['caption'] = match.group(1)
                                        print(f"Found caption in mdls {field}: {photo_data['caption']}")
                                        break
                except Exception as e:
                    print(f"Error running mdls: {str(e)}")
            
            # For macOS, try using sips command to extract metadata if no caption found
            if not photo_data['caption'] and os.path.exists('/usr/bin/sips'):
                try:
                    # Use macOS built-in sips command to extract all metadata
                    result = subprocess.run(
                        ['/usr/bin/sips', '-j', 'metadata', photo_path], 
                        capture_output=True, 
                        text=True, 
                        check=False
                    )
                    
                    # Parse the output if command was successful
                    if result.returncode == 0 and result.stdout:
                        # Look for description-related fields in raw output
                        if 'description' in result.stdout.lower():
                            # Try to extract description with regex - safer than parsing as JSON
                            match = re.search(r'"[dD]escription"\s*:\s*"([^"]+)"', result.stdout)
                            if match:
                                photo_data['caption'] = match.group(1)
                                print(f"Found caption in sips metadata: {photo_data['caption']}")
                except Exception as e:
                    print(f"Error running sips: {str(e)}")
                    # Continue with processing even if sips fails
            
            # Check if there's a .AAE sidecar file (used by iOS for edits/metadata)
            aae_path = os.path.splitext(photo_path)[0] + '.AAE'
            if not photo_data['caption'] and os.path.exists(aae_path):
                try:
                    with open(aae_path, 'r') as f:
                        aae_content = f.read()
                        # Look for description in the XML
                        match = re.search(r'<string name="description">([^<]+)</string>', aae_content)
                        if match:
                            photo_data['caption'] = match.group(1)
                            print(f"Found caption in AAE file: {photo_data['caption']}")
                except Exception as e:
                    print(f"Error reading AAE file: {str(e)}")
        
        except Exception as e:
            print(f"Error processing {photo_path}: {str(e)}")
        
    # If still no caption found, use filename as fallback
    if not photo_data['caption']:
        # Check if it has a date in the filename (common for iPhone photos)
        date_match = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', photo_data['filename'])
        if date_match:
            try:
                # Extract date from filename
                year, month, day = date_match.groups()
                date_obj = datetime(int(year), int(month), int(day))
                date_str = date_obj.strftime("%B %d, %Y")
                
                # Use date as part of the caption
                photo_data['caption'] = f"Photo taken on {date_str}"
                print(f"Using date-based caption: {photo_data['caption']}")
            except:
                # If date parsing fails, fall back to filename
                filename_without_ext = os.path.splitext(photo_data['filename'])[0]
                clean_name = re.sub(r'^IMG_', '', filename_without_ext)
                clean_name = clean_name.replace('_', ' ')
                photo_data['caption'] = clean_name
                print(f"Using filename-based caption: {photo_data['caption']}")
        else:
            # Remove file extension and replace underscores with spaces
            filename_without_ext = os.path.splitext(photo_data['filename'])[0]
            clean_name = re.sub(r'^IMG_', '', filename_without_ext)
            clean_name = clean_name.replace('_', ' ')
            photo_data['caption'] = clean_name
            print(f"Using filename-based caption: {photo_data['caption']}")
    
    # Always use ExifTool for metadata (most reliable across file types)
    exiftool_metadata = get_heic_metadata_with_exiftool(photo_path)
    
    # Extract GPS data
    tags = None
    if not is_heic:
        try:
            with open(photo_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
        except Exception as e:
            print(f"Error reading EXIF data: {str(e)}")
    
    # Get GPS coordinates with better extraction
    latitude, longitude = extract_gps_data(tags, exiftool_metadata, photo_path)
    
    # Store GPS data in photo_data if available
    if latitude is not None and longitude is not None:
        photo_data['latitude'] = latitude
        photo_data['longitude'] = longitude
        print(f"Stored GPS coordinates: {latitude}, {longitude}")
    
    # Extract orientation data
    orientation = extract_orientation_data(tags, exiftool_metadata)
    
    # Store orientation in photo_data if available
    if orientation is not None:
        photo_data['orientation'] = orientation
        print(f"Stored orientation: {orientation}")
    
    return photo_data

def extract_metadata_from_photos(photo_paths):
    """
    Extract metadata from multiple photos.
    
    Args:
        photo_paths (list): List of paths to photo files
        
    Returns:
        list: List of dictionaries containing photo data
    """
    photo_data_list = []
    
    for photo_path in photo_paths:
        photo_data = extract_metadata_from_photo(photo_path)
        photo_data_list.append(photo_data)
    
    return photo_data_list

def cleanup_temp_files(photo_data_list):
    """
    Clean up any temporary files created during processing.
    
    Args:
        photo_data_list (list): List of photo data dictionaries
    """
    if photo_data_list is None:
        return
        
    for photo_data in photo_data_list:
        if photo_data and photo_data.get('temp_file') and os.path.exists(photo_data['temp_file']):
            try:
                os.unlink(photo_data['temp_file'])
            except Exception as e:
                print(f"Error removing temp file {photo_data['temp_file']}: {str(e)}")
