import os
from PIL import Image
from const import IMAGE_TYPE
from tc_config import COS_MAIN_WEBSITE_PIC_BED_PATH, COS_REGION, COS_SECRET_ID, COS_SECRET_KEY, COS_SCHEMA, COS_TOKEN, \
    COS_OSU_BUCKET
from qcloud_cos import CosConfig, CosServiceError
from qcloud_cos import CosS3Client
from qcloud_cos.cos_threadpool import SimpleThreadPool

from loguru import logger

config = CosConfig(
    Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY,
    Token=COS_TOKEN, Scheme=COS_SCHEMA
)
client = CosS3Client(config)


def get_modification_time(filepath):
    return os.path.getmtime(filepath)


# 遍历文件夹并分类
def categorize_images(directory):
    image_dict = {}  # 存储分类图片的字典

    # 遍历目录及其子目录
    for root, dirs, files in os.walk(directory):
        # 遍历当前目录下的所有文件
        for file in sorted(files, key=lambda x: get_modification_time(os.path.join(root, x)), reverse=True):
            if "primitive" not in root:
                continue
            # 检查文件扩展名是否为图片格式
            if file.endswith(IMAGE_TYPE):
                # 获取图片文件的完整路径
                image_path = os.path.join(root, file)
                # 获取分类文件夹的名称
                category = os.path.basename(root.replace("\primitive", ""))
                # 将图片路径添加到对应分类的列表中
                image_dict.setdefault(category, []).append(image_path)

    return image_dict


def push_obj(cos_object_key, local_file):
    try:
        _ = client.head_object(Bucket=COS_OSU_BUCKET, Key=cos_object_key)
        # logger.info(f"File {cos_object_key} exists in cos.....")
        return None
    except CosServiceError as e:
        if e.get_status_code() == 404:
            exists = False
            # logger.info(f"File {cos_object_key} not exists in cos, upload it")
        else:
            logger.error("Error happened, reupload it.")
    if local_file.lower().endswith(IMAGE_TYPE):
        # https://cloud.tencent.com/document/product/436/55344
        logger.info(f"Local: {local_file}")
        ans = client.ci_put_object_from_local_file(
            COS_OSU_BUCKET, local_file, cos_object_key,
            PicOperations=f'{{"is_pic_info":1,"rules":[{{"fileid":"{cos_object_key}","rule":"imageMogr2/format/webp"}}]}}'
        )  # 上传时转为webp
        return ans
    else:
        # return client.upload_file(COS_OSU_BUCKET, cos_object_key, local_file)
        # 只上传图片
        pass


def upload_to_cos_bed(directory):
    image_dict = categorize_images(directory)
    # print(image_dict)
    # 遍历分类字典并打印元素
    for category, images in image_dict.items():
        output_directory = os.path.join(directory, category, "compressed")
        # 创建上传的线程池
        pool = SimpleThreadPool()
        total = len(images)
        index = 0
        for image_path in images:
            image_name_with_format = os.path.basename(image_path)
            # image_name = os.path.splitext(image_name_with_format)[0]
            # 加载图片
            img_obj = Image.open(image_path)
            # 创建输出目录（如果不存在）
            os.makedirs(output_directory, exist_ok=True)
            compressed_path = os.path.join(output_directory, image_name_with_format)
            if not os.path.exists(compressed_path):  # 缩小并压缩图片并保存到输出目录
                image_size = os.stat(image_path).st_size  # 获取图片大小
                width, height = img_obj.size  # 调整图片尺寸
                new_width = 512
                new_height = int(height * new_width / width)
                resized_img = img_obj.resize((new_width, new_height))
                resized_img.save(compressed_path, optimize=True, quality=50)
            cos_page_index = index // 4
            # 存储到cos
            cos_object_key_primitive = f"/{COS_MAIN_WEBSITE_PIC_BED_PATH}/{category}/primitive/{cos_page_index};{image_name_with_format}"
            cos_object_key_compressed = f"/{COS_MAIN_WEBSITE_PIC_BED_PATH}/{category}/compressed/{cos_page_index};{image_name_with_format}"
            pool.add_task(push_obj, cos_object_key_primitive, image_path)
            pool.add_task(push_obj, cos_object_key_compressed, compressed_path)
            index += 1
        pool.wait_completion()
        result = pool.get_result()
        if not result['success_all']:
            logger.error("Not all files upload sucessed. you should retry")
        else:
            logger.success(f"{category} upload sucessed.")


def tencent_cos_main_website_pic_bed_list(prefix) -> list:
    response = client.list_objects(
        Bucket=COS_OSU_BUCKET,
        Prefix=prefix,
        Delimiter='/',
        MaxKeys=100,
    )
    category_list = list()
    print(response)
    # 打印子目录
    if 'CommonPrefixes' in response:
        for folder in response['CommonPrefixes']:
            category_list.append(folder['Prefix'][len(prefix):][:-1])
    return category_list


def get_main_website_pic_bed_categories():
    return tencent_cos_main_website_pic_bed_list("main_website_pic_bed/")


if __name__ == '__main__':
    # 主站的图床管理工具
    upload_to_cos_bed("E:\坚果云\图片\网站图床")
    print(tencent_cos_main_website_pic_bed_list("main_website_pic_bed/"))
    print(tencent_cos_main_website_pic_bed_list("main_website_pic_bed/lolm/primitive/"))
    # pass