

while(1):
    decimal_number = int(input("请输入一个不超过100000000的十进制数字："))
    if decimal_number > 100000000:
        print("输入的数字超过了限制，请重新输入。")
    else:
        base_26_string = decimal_to_26_base(decimal_number)
        print(f"转换后的26进制字符串为：{base_26_string}")