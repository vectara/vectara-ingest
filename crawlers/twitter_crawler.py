import logging
from core.crawler import Crawler
import json
import tweepy
import re

def get_username_from_id(client, user_id):
    # Use the get_user method to retrieve the username based on the author_id
    user = client.get_user(id=user_id)
    return user.data.username if user else None

def clean_tweet(tweet: str) -> str:
    # Remove mentions that start with @
    cleaned_tweet = re.sub(r'@\w+', '', tweet)
    
    # Optional: remove extra spaces that may result from mention removals
    cleaned_tweet = re.sub(r'\s+', ' ', cleaned_tweet).strip()
    
    return cleaned_tweet

class TwitterCrawler(Crawler):
    def crawl(self) -> None:

        bearer_token = self.cfg.twitter_crawler.twitter_bearer_token
        num_tweets = self.cfg.twitter_crawler.num_tweets
        userhandles = self.cfg.twitter_crawler.userhandles
        client = tweepy.Client(bearer_token=bearer_token)

        for username in userhandles:
            user = client.get_user(username=username)        
            query = f'@{username} -is:retweet'  # Exclude retweets
            tweets = client.search_recent_tweets(query=query, 
                                                 tweet_fields=['public_metrics', 'author_id', 'lang', 'geo', 'entities'], 
                                                 max_results=num_tweets)
            
            doc = {
                "documentId": 'tweets-' + username,
                "title": f'top {num_tweets} tweets of {username}',
                "metadataJson": json.dumps({ 
                    'url': f'https://twitter.com/{username}',
                    'source': 'twitter',
                    'username': username,
                    'account_created_at': user.data.created_at,
                    'followers_count': user.data.public_metrics['followers_count'] if user.data.public_metrics else None,
                    'following_count': user.data.public_metrics['following_count'] if user.data.public_metrics else None,
                    'tweet_count': user.data.public_metrics['tweet_count'] if user.data.public_metrics else None,
                    'description': user.data.description,
                    'location': user.data.location,
                    'verified': user.data.verified,
                }),
                "section": []
            }
            for tweet in tweets.data:
                doc["section"].append({ 
                    "text": clean_tweet(tweet.text) if self.cfg.twitter_crawler.get("clean_tweets", True) else tweet.text,
                    "metadataJson": json.dumps({
                        "author": get_username_from_id(client, tweet.author_id),
                        "created_at": tweet.created_at,
                        "retweet_count": tweet.public_metrics['retweet_count'] if tweet.public_metrics else None,
                        "reply_count": tweet.public_metrics['reply_count'] if tweet.public_metrics else None,
                        "like_count": tweet.public_metrics['like_count'] if tweet.public_metrics else None,
                        "quote_count": tweet.public_metrics['quote_count'] if tweet.public_metrics else None,
                        "lang": tweet.lang
                    }),
                })
            succeeded = self.indexer.index_document(doc)            
            if succeeded:
                logging.info(f"Indexed tweets for {username}")
            else:
                logging.info(f"Error indexing  tweets for {username}")
        logging.info(f"Finished indexing all users (total={len(userhandles)})")

