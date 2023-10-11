import pathlib
import boto3
import os
from typing import List, Tuple

from core.crawler import Crawler
from slugify import slugify

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

        os.environ['AWS_ACCESS_KEY_ID'] = self.cfg.s3_crawler.aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.cfg.s3_crawler.aws_secret_access_key

        bucket, key = split_s3_uri(folder)
        s3_files = list_files_in_s3_bucket(bucket, key)

        # process all files
        s3 = boto3.client('s3')
        for s3_file in s3_files:
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
                self.indexer.index_file(filename=local_fname, uri=url, metadata=metadata)
