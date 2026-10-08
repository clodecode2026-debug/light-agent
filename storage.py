import os
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
import logging

logger = logging.getLogger(__name__)

class S3StorageManager:
    def __init__(self):
        self.endpoint_url = os.environ.get("S3_ENDPOINT", "https://gateway.storjshare.io")
        self.access_key = os.environ.get("S3_ACCESS_KEY")
        self.secret_key = os.environ.get("S3_SECRET_KEY")
        self.bucket_name = os.environ.get("S3_BUCKET", "agent-files")
        self.region_name = os.environ.get("S3_REGION", "us-east-1")
        
        self.s3_client = None
        if self.access_key and self.secret_key:
            try:
                # Для Storj S3 Gateway критически важно использовать signature_version='s3'
                # и addressing_style='path' для правильной отправки заголовка Content-Length
                cfg = Config(signature_version="s3", s3={"addressing_style": "path"})
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region_name,
                    config=cfg,
                    verify=False
                )
                logger.info(f"S3 Storj storage client успешно инициализирован (bucket: {self.bucket_name})")
            except Exception as e:
                logger.error(f"Ошибка инициализации S3 клиента: {e}")

    def upload_file_bytes(self, file_bytes: bytes, filename: str, content_type: str = "audio/mpeg") -> str:
        if not self.s3_client:
            logger.warning("S3 клиент не инициализирован (отсутствуют ключи S3_ACCESS_KEY / S3_SECRET_KEY)")
            return ""
        
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=file_bytes,
                ContentLength=len(file_bytes),
                ContentType=content_type
            )
            file_url = f"{self.endpoint_url}/{self.bucket_name}/{filename}"
            logger.info(f"Файл успешно загружен в S3 Storj: {file_url} (размер: {len(file_bytes)} байт)")
            return file_url
        except (BotoCoreError, ClientError) as e:
            logger.error(f"Ошибка загрузки файла в S3: {e}")
            return ""

    def test_connection(self) -> bool:
        if not self.s3_client:
            return False
        try:
            test_content = b"Storj keepalive check"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key="storj_healthcheck.txt",
                Body=test_content,
                ContentLength=len(test_content),
                ContentType="text/plain"
            )
            return True
        except Exception as e:
            logger.error(f"Storj healthcheck error: {e}")
            return False

s3_storage = S3StorageManager()
