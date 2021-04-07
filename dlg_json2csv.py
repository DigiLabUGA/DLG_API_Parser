import argparse
import sys
import requests
import csv
import re
import pandas as pd


def dlg_json2list(url_list):
    list_json = []

    for url in url_list:

        # Checking for .json already in URL before we assume it is not there.
        is_api_url = type(re.search('.json', url)) == re.Match

        # Checking to see if URL is a search result or a single item.
        is_search_result = type(re.search('\?', url)) == re.Match
        url_old = url

        if not is_api_url:
            # If this is reached, then '.json' is not present and we need to add it to the URL to grab API response.
            if is_search_result:
                api_url = re.sub('\?', '.json?', url)

            else:
                api_url = re.sub('$', '.json', url)
        else:
            # If this is reached, then the URL is already the API response.
            api_url = url

        # Grabbing the response JSON.
        try:
            # The error check was important because of the older version, but I will keep it just in case. Now that I
            # implemented reading the urls from the file instead of the command line, majority of the potential
            # errors have been alleviated.
            response = requests.get(api_url)
            json_dict = response.json()
        except:
            print('Something went wrong with the url')
            print('{} is the url you are trying to parse.'.format(url_old))
            continue

        json_dict = response.json()

        if not is_search_result:
            list_json.append(json_dict['response']['document'])
        # If the URL is a search query, then we need to grab every item on every page.
        else:
            total_pages = json_dict['response']['pages']['total_pages']
            current_page = json_dict['response']['pages']['current_page']
            next_page = json_dict['response']['pages']['next_page']

            # This loop will add each dictionary to the list and the prepare the next URL for the next iteration.
            while True:

                for dict in json_dict['response']['docs']:
                    list_json.append(dict)

                next_page_str = 'page=' + str(next_page)

                # Changing the page number in the search results.
                if type(re.search('page=\d+', api_url)) == re.Match:
                    api_url = re.sub('page=\d+', next_page_str, api_url)
                else:
                    # Should only be entered the first iteration, the remaining links should already contain
                    # 'page=\d' from previous iteration.
                    next_page_str = '?' + next_page_str + '&'
                    api_url = re.sub('\?', next_page_str, api_url)

                # Grabbing the response and JSON.
                try:
                    response = requests.get(api_url)
                    json_dict = response.json()
                except:
                    print('Something happened on page {} of this URL: {}'.format(next_page + 1,
                                                                                 re.sub('\.json', '', api_url)))

                # Updating variables.
                current_page = json_dict['response']['pages']['current_page']
                next_page = json_dict['response']['pages']['next_page']

                # This is the condition that will end the while loop. So once current_page is the same at
                # total_pages, grab the last amount of dictionaries and break the loop.
                if current_page == total_pages:
                    for dict in json_dict['response']['docs']:
                        list_json.append(dict)
                    break

    # Error Check. list_json should have 1 or more items inside. Otherwise exit.
    if len(list_json) < 1:
        print('Was not able to grab any of the URLs. Please check them.')
        sys.exit()

    '''This loop with iterate through each item of list_json to convert each item into a string so when creating the 
    CSV, the excess quotation marks and brackets will go away. Plus we will handle the redirecting URLs and copyright 
    issues with replacing the item with the thumbnails. '''
    for item in list_json:
        for key in item.keys():

            # Changing the list into one big string.
            if type(item[key]) == list:
                text = item[key][0]
                for i in range(1, len(item[key])):
                    text += ', ' + item[key][i]
                item[key] = text

            # Changing the item URL.
            if key == 'edm_is_shown_by':
                # Thumbnails.
                if item[key] == None:
                    thumbnail_url = 'https://dlg.galileo.usg.edu/'
                    try:
                        repoID, collectionID, itemID = item['id'].split('_', 2)
                    except:
                        print(item['id'])
                    thumbnail_url += repoID + '/' + collectionID + '/do-th:' + itemID

                    # Now grabbing the redirected URL.
                    item[key] = requests.get(thumbnail_url).url
                else:
                    # Grabbing the redirected item.
                    try:
                        item[key] = requests.get(item[key]).url
                    except:
                        print(item[key])

    return list_json


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Makes requests to the DLG \
                        API to then parse into a CSV. Then mapped to follow the \
                        DLGs column mapping to be uploaded into Omeka via CSV Import')

    parser.add_argument('--input', dest='input', type=str, required=True,
                        help=' The file that contains the URLs. \
                        Make sure there is one URL on each line of the file.')
    parser.add_argument('--output', dest='output', type=str, required=True,
                        help='The name of the output CSV file.')
    parser.add_argument('--encode', dest='encode', type=str, default='utf-8',
                        help='The encoding preferred when writing to csv. [Default: UTF-8]')
    parser.add_argument('--mapping', dest='dlg', type=str, default='DLG_Mapping.csv',
                        help='The name of the dlg mapping CSV for column headings. \
                        Default: DLG_Mapping.csv')
    args = parser.parse_args()

    url_file = args.input   # The file of URLs from the DLG.
    csv_name = args.output  # The name of the CSV output file.
    encoding = args.encode  # File encoding.
    dlg_mapping = args.dlg  # What to map the DLG's field names to.

    # Grabbing all of the URLs in the file to then be parsed.
    url_list = []
    with open(url_file, 'r') as dlg_urls:
        for line in dlg_urls:
            url_list.append(line.strip())

    # Grabbing the complete list of JSONs from the provided URLs and making a dataframe.
    list_json = dlg_json2list(url_list)
    df = pd.DataFrame.from_dict(list_json)

    # Initializing the DLG Mapping dict.
    new_column_name = {}

    # Grabbing the DLG Dublin Core Mapping.
    with open(dlg_mapping, 'r') as map_csv:
        w = csv.reader(map_csv)
        for row in w:
            new_column_name.update({row[0]: row[1]})

    # Dropping columns from the dataframe if they are not in the DLG Mapping.
    drop_columns = [col for col in list(df.columns) if col not in list(new_column_name.keys())]
    df.drop(drop_columns, axis=1, inplace=True)

    # Renaming the columns to map to Dublin Core and writing to CSV.
    df.rename(columns=new_column_name, inplace=True)
    df = df.sort_index(axis=1)
    df.to_csv(csv_name, index=False)
