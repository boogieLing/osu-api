import os
import shutil

from qcloud_cos.cos_threadpool import SimpleThreadPool

from const import COS_REGION, COS_SECRET_ID, COS_SECRET_KEY, COS_TOKEN, COS_SCHEMA, COS_OSU_BUCKET, COS_OSU_PATH, \
    IMAGE_TYPE
from qcloud_cos import CosConfig, CosServiceError
from qcloud_cos import CosS3Client
from loguru import logger

# pip install -U cos-python-sdk-v5

config = CosConfig(
    Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY,
    Token=COS_TOKEN, Scheme=COS_SCHEMA
)
client = CosS3Client(config)


def push_obj(category_key, cos_object_key, local_file):
    if local_file.lower().endswith(IMAGE_TYPE):
        # https://cloud.tencent.com/document/product/436/55344
        ans = client.ci_put_object_from_local_file(
            COS_OSU_BUCKET, local_file, cos_object_key,
            PicOperations=
            f'{{"is_pic_info":1,"rules":[{{"fileid":"{cos_object_key}","rule":"imageMogr2/format/webp"}}]}}'
        )  # 上传时压缩
        # 图片存两份，在主目录也需要一份
        ans = client.ci_put_object_from_local_file(
            COS_OSU_BUCKET, local_file, category_key,
            PicOperations=
            f'{{"is_pic_info":1,"rules":[{{"fileid":"{category_key}","rule":"imageMogr2/format/webp"}}]}}'
        )  # 上传时压缩
        return ans
    else:
        # return client.upload_file(COS_OSU_BUCKET, cos_object_key, local_file)
        # 只上传图片
        pass


def tencent_cos_upload(category, upload_dir, beatMap_name):
    g = os.walk(upload_dir)
    # 创建上传的线程池
    pool = SimpleThreadPool()
    for path, dir_list, file_list in g:
        for file_name in file_list:
            src_key = os.path.join(path, file_name)
            cos_object_key = f"/{COS_OSU_PATH}/{category}/{beatMap_name}/{file_name.strip('/')}"
            category_key = f"/{COS_OSU_PATH}/{category}/imgs/{beatMap_name}#{file_name.strip('/')}"
            # 判断 COS 上文件是否存在
            exists = False
            try:
                _ = client.head_object(Bucket=COS_OSU_BUCKET, Key=cos_object_key)
                exists = True
            except CosServiceError as e:
                if e.get_status_code() == 404:
                    exists = False
                else:
                    logger.error("Error happened, reupload it.")
            if not exists:
                logger.info(f"File {src_key} not exists in cos, upload it")
                # push_obj(cos_object_key, src_key)
                pool.add_task(push_obj, category_key, cos_object_key, src_key)

    pool.wait_completion()
    result = pool.get_result()
    if not result['success_all']:
        logger.error("Not all files upload sucessed. you should retry")
    else:
        logger.success(f"{upload_dir} upload sucessed.")
        # shutil.rmtree(upload_dir)
