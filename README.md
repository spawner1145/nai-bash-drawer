# nai bash drawer
批量跑图，保存到zip文件，并生成一个csv文件对应图片和tag，支持使用wildcard

用于刷数据集

kaggle地址https://www.kaggle.com/code/spawnerqwq/nai4drawer

## 特殊用法
#### 注意:是当作提示词用的

```yaml
<wda:x=y>
```
此指令会固定从名为x的wildcard中抽取y项，附加a的固定权重

```yaml
<wda-b:x=y>
```
此指令会从名为x的wildcard中抽取y项，附加a到b范围内的随机权重
如果权重参数（a-b或a）出现问题，默认为权重范围0到1

举例：
```yaml
<wd1:artist=1> # 随机抽一个画师，权重为1，例如wlop
<wd1:artist=2> # 随机抽两个画师，权重为1，例如wlop,torino aqua
<wd0.5:artist=2> # 随机抽两个画师，权重为0.5，例如(wlop:0.5),(torino aqua:0.5)
<wd0.4-0.5:artist=3> # 随机抽3个画师，权重为0.4到0.5中的随机数，例如(a:0.4111),(b:0.4231),(c:0.4342)
<wd1:artist=2>,<wd0.6:artist=3> # 随机抽五个画师，两个权重为1，三个权重为0.6
```
