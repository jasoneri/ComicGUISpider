import requests
import re


def get_proxy():
    resp = requests.get('http://192.168.199.223:5566/random')
    proxy = re.search(r'\d+.\d+.\d+.\d+:\d+', resp.text)[0]
    return proxy


def print_dynamic(total):
    total += 1  # 后台看进度打印
    sign = {1: '→', 2: '↘', 3: '↓', 4: '↙', 5: '←', 6: '↖', 7: '↑', 0: '↗', 999: '\n'}
    p = sign[total % (len(sign.keys()) - 1)] if total % 50 else sign[999]
    print(p, end='', flush=True)
    return total


if __name__ == '__main__':
    print(get_proxy())