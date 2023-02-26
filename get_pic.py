import time

from get import osu_pic

if __name__ == '__main__':
    for i in range(12):
        print(osu_pic.random_pic())
        time.sleep(1)
