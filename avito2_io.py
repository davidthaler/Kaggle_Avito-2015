'''
This file contains input output code that runs against the large .tsv files.

author: David Thaler
date: July 2015
'''
import csv
import os
import pdb
import cPickle
import datetime
import re
import features

BASE = '/Users/davidthaler/Documents/Kaggle/avito2'
DATA = os.path.join(BASE, 'data')
PROCESSED = os.path.join(DATA, 'processed')
ARTIFACTS = os.path.join(BASE, 'artifacts')
TRAIN = os.path.join(DATA, 'trainSearchStream.tsv')
TEST = os.path.join(DATA, 'testSearchStream.tsv')
SEARCH_INFO = os.path.join(DATA, 'SearchInfo.tsv')
ADS_INFO = os.path.join(DATA, 'AdsInfo.tsv')
SUBMIT = os.path.join(BASE, 'submissions')
VISIT = os.path.join(DATA, 'VisitsStream.tsv.gz')
PHONE = os.path.join(DATA, 'PhoneRequestsStream.tsv.gz')

def join_with_ads(use_train, 
                  ads,
                  train_etl, 
                  search_etl, 
                  ads_etl,
                  do_validation=False,
                  val_ids=None):
  '''
  A generator that performs a rolling join on SearchID over the files 
  trainSearchStream.tsv (or testSearchStream.tsv) and SearchInfo.tsv, and
  a join-by-key with the dictionary of context ads generated by parseAds.py, 
  then extracts features, and returns one row for each contextual ad. 
  Each row contains a dict of features, and a label, which is 0 for test.
  
  NB: ads[AdID] is an int
  
  args:
    use_train - if True, use trainSearchStream.tsv, if false, use 
        testSearchStream.tsv
    ads - the dictionary of context ads and their attributes generated 
        by parseAds.py
    train_etl - a dict of lambdas or functions that extracts data from 
        each line of train and transforms it as needed. To emit labels,
        include the label field in train_etl.
    search_etl - a dict of lambdas or functions that extracts data from 
        each line of SearchInfo and transforms it as needed.
    ads_etl - a dict of lambdas or functions that extract data from the
        values from the ads dict.
    do_validation - Default False. If True and val_ids is not None,
        emit the validation set lines. Else emit all lines.
        Ignored if val_ids is None.
    val_ids - a set of ints or None. If do_validation is True, emit only
        lines with search id in val_ids. If do_validation is False,
        skip these lines. If val_ids is None, emit all lines.
        
  return:
    a generator that emits a feature vector and a label for each row
  '''
  path = TRAIN if use_train else TEST
    
  with open(path) as f_t:
    with open(SEARCH_INFO) as f_si:
      read_t  = csv.DictReader(f_t, delimiter='\t')
      read_si = csv.DictReader(f_si, delimiter='\t')
      si_line = read_si.next()
      for (k, t_line) in enumerate(read_t):
        search_id = t_line['SearchID']
        while search_id != si_line['SearchID']:
          si_line = read_si.next()
        # At this point, the SearchID's should match
        sid = int(search_id)
        if val_ids is not None:
          if do_validation and sid not in val_ids:
            continue
          if not do_validation and sid in val_ids:
            continue
        if int(t_line['ObjectType']) == 3:
          line = {}
          ad = ads[int(t_line['AdID'])]
          for field in train_etl:
            line[field] = train_etl[field](t_line)
          for field in search_etl:
            line[field] = search_etl[field](si_line)
          for field in ads_etl:
            line[field] = ads_etl[field](ad)
          y = int(t_line['IsClick']) if use_train else 0
          yield line, y


def rolling_join(use_train, 
                 train_etl, 
                 search_etl, 
                 do_validation=False,
                 val_ids=None,
                 context_only=True, 
                 verbose=False):
  '''
  A generator that performs a rolling join on SearchID over the files 
  trainSearchStream.tsv (or testSearchStream.tsv) and SearchInfo.tsv, 
  extracts features, and returns each row, or one row for each contextual ad.
  Each row contains a dict of features, and a label, which is 0 for the 
  test set.
  
  args:
    use_train - if True, use trainSearchStream.tsv, if false, use 
        testSearchStream.tsv
    train_etl - a dict of lambdas or functions that extracts data from 
        each line of train and transforms it as needed. To emit labels,
        include the label field in train_etl.
    search_etl - a dict of lambdas or functions that extracts data from 
        each line of SearchInfo and transforms it as needed.
    do_validation - Default False. If True and val_ids is not None,
        emit the validation set lines. Else emit all lines.
        Ignored if val_ids is None.
    val_ids - a set of ints or None. If do_validation is True, emit only
        lines with search id in val_ids. If do_validation is False,
        skip these lines. If val_ids is None, emit all lines.
    context_only - Default True. If true, only returns contextual ads.
    verbose - Default False. If True, print a line count each 1M rows.
    
  return:
    a generator that emits a feature vector and a label for each row
  '''
  path = TRAIN if use_train else TEST
    
  with open(path) as f_t:
    with open(SEARCH_INFO) as f_si:
      read_t  = csv.DictReader(f_t, delimiter='\t')
      read_si = csv.DictReader(f_si, delimiter='\t')
      si_line = read_si.next()
      for (k, t_line) in enumerate(read_t):
        if verbose and ((k + 1) % 1000000 == 0):
          print 'read %d lines' % (k + 1)
        search_id = t_line['SearchID']
        while search_id != si_line['SearchID']:
          si_line = read_si.next()
        # At this point, the SearchID's should match
        if val_ids is not None:
          sid = int(search_id)
          if do_validation and sid not in val_ids:
            continue
          if not do_validation and sid in val_ids:
            continue
        if (not context_only) or (int(t_line['ObjectType']) == 3):
          line = {}
          for field in train_etl:
            line[field] = train_etl[field](t_line)
          for field in search_etl:
            line[field] = search_etl[field](si_line)
          y = int(t_line['IsClick']) if use_train else 0
          yield line, y


def sample_search_info_by_user(fraction, maxlines=None, etl=None):
  '''
  Reads the file SearchInfo.tsv and selects a sample of users by value.
  By default, creates a dictionary with the sampled UserID's as values 
  and the SearchID's for those users as keys. Optionally, it can return
  a list of fields extracted and transformed using a list of lambdas or
  functions.
  
  time: 10+ minutes, ~5 min. in pypy
  
  args:
    fraction - int. 1/fraction of users will be sampled
    maxlines - the maximum # of lines to read, or None for all lines
    etl - a list of functions/lambdas that extract and transform
      fields in SearchInfo.
      See user2.py for an example of etl usage.
    
  return:
    a dict with SearchIDs for keys and UserIDs for values
  '''
  out = {}
  with open(SEARCH_INFO) as fsi:
    read_si = csv.DictReader(fsi, delimiter='\t')
    for (k, line) in enumerate(read_si):
      if k == maxlines:
        break
      if (k + 1) % 1000000 == 0:
        print '%d rows read' % (k + 1)
      if(hash(line['UserID']) % fraction) == 0:
        if etl is None:
          out[int(line['SearchID'])] = int(line['UserID'])
        else:
          values = [fn(line) for fn in etl]
          out[int(line['SearchID'])] = values
  return out


def train_sample(user_sample, maxlines=None, context_only=True, etl={}):
  '''
  Replaces sample_train_by_user.
  Reads trainSearchStream, filtering for searches by users in user_sample,
  then joins in fields from user_sample using a dict from field names to
  functions/lambda for extraction/transformation.
  
  time: ~12 min in pypy
  
  args:
    user_sample - a dict like {SearchID: list of features}. 
        SearchID is an int. 
        This dict can be returned from sample_search_info_by_user.
    etl - a dict like {'Field name':function or lambda}. 
        The lambda takes the whole list of features, and extracts the correct
        value for 'Field Name', transforming it if needed.
    maxlines - the maximum # of lines to read, (or None for all lines)
      in the file trainSearchStream.tsv
    context_only - Default True. If true, only returns contextual ads.
    
  returns:
    a generator with the joined and filtered rows
  '''
  with open(TRAIN) as f_in:
    train_reader = csv.DictReader(f_in, delimiter='\t')
    for (k, line) in enumerate(train_reader):
      if k == maxlines:
        break
      sid = int(line['SearchID'])
      if sid in user_sample:
        if (not context_only) or (int(line['ObjectType']) == 3):
          join_values = user_sample[sid]
          for field in etl:
            line[field] = etl[field](join_values)
          yield line


def put_artifact(obj, artifactfile):
  '''
  Pickles an object at ARTIFACTS/artifactfile
  
  args:
    obj - an intermediate result to pickle
    artifactfile - obj is pickled at ARTIFACT/artifactfile
  
  return:
    nothing, but obj is pickled at ARTIFACT/artifactfile
  '''
  artifactpath = os.path.join(ARTIFACTS, artifactfile)
  with open(artifactpath, 'w') as f:
    cPickle.dump(obj, f)


def get_artifact(artifactfile):
  '''
  Recovers a pickled intermediate result (artifact) from ARTIFACTS/
  
  args:
    artifactfile - an object is loaded from ARTIFACTS/artifactfile 
    
  return:
    the reloaded intermediate object
  '''
  artifactpath = os.path.join(ARTIFACTS, artifactfile)
  with open(artifactpath) as f:
    artifact = cPickle.load(f)
  return artifact


def convert_date(date_str):
  '''
  Converts a string-formatted date in the format used in the Avito (2015)
  data to a datetime.datetime.
  
  args:
    date_str - a string in the date format 'YYYY-mm-DD HH:MM:SS.S'
    
  return:
    a datetime.datetime with the date from date_str
  '''
  dt = re.split('\D', date_str)
  dt = [int(s) for s in dt[:6]]
  return datetime.datetime(*dt)


# NB: This has been run and saved at: ARTIFACTS/test_search_ids.pkl
def test_sids():
  '''
  Get a set with all of the SearchID's in the test set.
  
  time: several minutes.
  
  args:
    none
  
  returns:
    a set of all of the unique search ids in the file testSearchStream.tsv
  '''
  out = set()
  with open(TEST) as f:
    reader = csv.DictReader(f, delimiter='\t')
    for line in reader:
      out.add(int(line['SearchID']))
  return out
  
  
def extract_validation_ids(sample, test_ids=None):
  '''
  Finds the SearchID's of the last search by each user in sample. 
  These searches will form the validation set.
  
  time: 1-2 seconds
  
  args:
    sample - a Dict of {SearchID: values} where values must be [UserID, date, ...]
    test_ids - None or  a set of unique test set search ids. 
        Will create the set if None.
      
  return:
    a set of SearchID's for the last search by each user
  '''
  if test_ids is None:
    test_ids = test_sids()
  users = {}
  for key in sample:
    if key in test_ids:
      continue
    uid = sample[key][0]
    date = sample[key][1]
    if users.has_key(uid):
      if users[uid][1] < date:
        users[uid] = (key, date)
    else:
      users[uid] = (key, date)
  return {users[uid][0] for uid in users}


def full_val_set(test_ids, cutoff_date):
  '''
  Selects the last search in the train set for each user, provided that
  it occurs on or after cutoff_date. 
  
  args:
    test_ids - set of int. A set of SearchID's that occur in 
        testSearchStream.tsv (eg ARTIFACTS/test_search_ids.pkl)
    cutoff_date - str or datetime.datetime. Rows that have a SearchDate
        earlier than cutoff_date are not considered for the validation set
        
  return:
    a set of (int) SearchIDs that constitute a validation set.
  '''
  if type(cutoff_date) is str:
    cutoff_date = convert_date(cutoff_date)
  users = {}
  with open(SEARCH_INFO) as f_si:
    reader = csv.DictReader(f_si, delimiter='\t')
    for line in reader:
      sid = int(line['SearchID'])
      if sid in test_ids:
        continue
      date = convert_date(line['SearchDate'])
      if date < cutoff_date:
        continue
      uid = int(line['UserID'])
      if uid not in users or users[uid][1] < date:
        users[uid] = (sid, date)        
  return {users[uid][0] for uid in users}


# This is probably now dead code, but it is still referenced in split1.py:
  
def sample_train_by_user(fraction, 
                         user_sample=None,
                         max_searches=None, 
                         maxlines=None,
                         context_only=True):
  '''
  Gets the SearchID's for a sample (by value) of users, then returns a 
  generator that returns rows in trainSearchStream that are from the 
  sampled users. Joins the UserID on to the row.
  Optionally filters down to only contextual ads.
  
  NB: user_sample, if given, must be of the form {SearchID:UserID}, 
      with both ID's as ints.
  
  args:
    fraction - int. 1/fraction of users will be sampled
    user_sample - None or dict. If None, the sample of users is generated, 
      The dict must be of the form {SearchID:UserID}, with both ID's as ints.
    max_searched - the maximum # of lines to read, (or None for all lines)
      in the file SearchInfo.tsv
    maxlines - the maximum # of lines to read, (or None for all lines)
      in the file trainSearchStream.tsv
    context_only - Default True. If true, only returns contextual ads.
    
  returns:
    a generator with the joined and filtered rows
  '''
  if user_sample is None:
    user_sample = sample_search_info_by_user(fraction, max_searches)
  
  with open(TRAIN) as f_in:
    train_reader = csv.DictReader(f_in, delimiter='\t')
    for (k, line) in enumerate(train_reader):
      if k == maxlines:
        break
      sid = int(line['SearchID'])
      if sid in user_sample:
        line['UserID'] = str(user_sample[sid])                    
        if (not context_only) or (int(line['ObjectType']) == 3):
          yield line


      