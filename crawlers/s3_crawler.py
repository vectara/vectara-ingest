import pathlib
import boto3
import os
from typing import List, Tuple
import logging

from core.crawler import Crawler
from slugify import slugify
import pandas as pd

def list_files_in_s3_bucket(bucket_name: str, prefix: str) -> List[str]:
    """
    List all files in an S3 bucket.

    args:
        bucket_name: name of the S3 bucket
        prefix: the "folder" on S3 to list files from
    """
    s3 = boto3.client('s3')
    result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    files = []

    for content in result.get('Contents', []):
        files.append(content['Key'])

    while result.get('IsTruncated', False):
        continuation_key = result.get('NextContinuationToken')
        result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_key)

        for content in result.get('Contents', []):
            files.append(content['Key'])

    return files

def split_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Split an S3 URI into bucket and object key.
    """
    bucket_and_object = s3_uri[len("s3://"):].split("/", 1)
    bucket = bucket_and_object[0]
    object_key = bucket_and_object[1] if len(bucket_and_object) > 1 else ""
    return bucket, object_key

class S3Crawler(Crawler):
    """
    Crawler for S3 files.
    """
    def crawl(self) -> None:
        folder = self.cfg.s3_crawler.s3_path
        extensions = self.cfg.s3_crawler.extensions
        metadata_file = self.cfg.s3_crawler.get("metadata_file", None)

        s3 = boto3.client('s3')
        bucket, key = split_s3_uri(folder)

        if metadata_file:
            local_metadata_fname = slugify(metadata_file)
            s3.download_file(bucket, metadata_file, local_metadata_fname)
            df = pd.read_csv(local_metadata_fname)
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}
        self.model = None

        os.environ['AWS_ACCESS_KEY_ID'] = self.cfg.s3_crawler.aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.cfg.s3_crawler.aws_secret_access_key

        # process all files
        s3_files = list_files_in_s3_bucket(bucket, key)
        for s3_file in s3_files:
            if s3_file.endswith(metadata_file):
                continue
            file_extension = pathlib.Path(s3_file).suffix
            if file_extension in extensions or "*" in extensions:
                extension = s3_file.split('.')[-1]
                local_fname = slugify(s3_file.replace(extension, ''), separator='_') + '.' + extension
                s3.download_file(bucket, s3_file, local_fname)
                url = f's3://{bucket}/{s3_file}'
                metadata = {
                    'source': 's3',
                    'title': s3_file,
                    'url': url
                }
                if s3_file in metadata:
                    metadata.update(metadata.get(s3_file, {}))    
                if file_extension in ['.mp3', '.mp4']:
                    self.indexer.index_media_file(local_fname, metadata)
                else:
                   self.indexer.index_file(filename=local_fname, uri=url, metadata=metadata)
