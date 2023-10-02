import os
from PIL import Image
from const import IMAGE_TYPE
from tc_config import COS_MAIN_WEBSITE_PIC_BED_PATH, COS_REGION, COS_SECRET_ID, COS_SECRET_KEY, COS_SCHEMA, COS_TOKEN, \
    COS_OSU_BUCKET
from qcloud_cos import CosConfig, CosServiceError
from qcloud_cos import CosS3Client
from qcloud_cos.cos_threadpool import SimpleThreadPool
from datetime import datetime
import pytz

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
        # 按创建时间逆序排序
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
            # cos_page_index = index // 4
            cos_page_index = index
            cos_page_index = f'{cos_page_index:08d}'  # 补零保证1e8以内的顺序
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


def tencent_cos_main_website_pic_bed_list(prefix, maker, max_keys=30) -> list:
    if maker is not None:
        response = client.list_objects(
            Bucket=COS_OSU_BUCKET,
            Prefix=prefix,
            Delimiter='/',
            MaxKeys=max_keys,
            Marker=maker
        )
    else:
        response = client.list_objects(
            Bucket=COS_OSU_BUCKET,
            Prefix=prefix,
            Delimiter='/',
            MaxKeys=max_keys
        )
    return response


def get_main_website_pic_bed_categories(maker=None, max_keys=1000):
    prefix = f"{COS_MAIN_WEBSITE_PIC_BED_PATH}/"
    response = tencent_cos_main_website_pic_bed_list(prefix, maker, max_keys)
    category_list = []
    # 打印子目录
    if 'CommonPrefixes' in response:
        for folder in response['CommonPrefixes']:
            category_list.append(folder['Prefix'][len(prefix):][:-1])
    return category_list


def get_pic_bed_by_category(category, input_marker=None, max_keys=4):
    prefix = f"{COS_MAIN_WEBSITE_PIC_BED_PATH}/{category}/compressed/"
    response = tencent_cos_main_website_pic_bed_list(prefix, input_marker, max_keys)
    pic_list = []
    if "Contents" in response:
        for content in response["Contents"]:
            key = content["Key"]
            last_modified_time = content["LastModified"]
            last_semicolon_index = key.rfind(";")  # 查找最后一个分号的索引
            last_period_index = key.rfind(".")  # 查找最后一个句号的索引
            pic_name = key[last_semicolon_index + 1:last_period_index]  # 从最后一个分号的下一个位置
            # 创建datetime对象
            dt = datetime.strptime(last_modified_time, "%Y-%m-%dT%H:%M:%S.%fZ")
            # 设置原始时间的时区为UTC
            dt = dt.replace(tzinfo=pytz.UTC)
            # 转换时区为中国上海
            shanghai_tz = pytz.timezone("Asia/Shanghai")
            shanghai_time = dt.astimezone(shanghai_tz)
            pic_list.append({
                "name": pic_name,
                "url": f"https://r0picgo-1308801249.cos.ap-guangzhou.myqcloud.com/{key}",
                "last_modified": shanghai_time.strftime("%Y-%m-%d %H:%M:%S")
            })
    marker = None
    if response["IsTruncated"] != "false":
        marker = response["NextMarker"]
    return {
        "marker": marker,
        "data": pic_list
    }


if __name__ == '__main__':
    # 主站的图床管理工具
    # upload_to_cos_bed("C:\\Users\\hanyuanling\\Nutstore\\1\\图片\\网站图床")
    print(get_main_website_pic_bed_categories())
    res = get_pic_bed_by_category("测试")
    print(res)
    res = get_pic_bed_by_category("测试", input_marker=res["marker"])
    print(res)
    res = get_pic_bed_by_category("测试", input_marker=res["marker"])
    print(res)
    # print(tencent_cos_main_website_pic_bed_list(f"{COS_MAIN_WEBSITE_PIC_BED_PATH}/测试/primitive/", maker=None))
    # pass
