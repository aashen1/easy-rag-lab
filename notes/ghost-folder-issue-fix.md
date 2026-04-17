# 问题

> 2026年4月18日

这个项目跑着跑着，根目录就会多出一个`output_dir`空文件夹，里面也不会产生东西，删了再跑一会儿又会出来。又因为这个名字在代码里使用太多，AI尝试排查了一会儿没有成功。

# AI分析

找Qwen要了一套方案，见 [chat-幽灵文件夹排查指南.md](chat-幽灵文件夹排查指南.md) 

先让AI按照这个方案在python代码里埋了钩子，但没能成功捕获，不知道是代码运作不对，还是日志系统记录不完整。

于是又下载了`Process Monitor`，按`Ctrl+L`，设置过滤条件：

```
Operation is CreateFile
Result is SUCCESS
Path ends with output_dir
```

点击`Apply`，然后继续跑测试。

目前已经确定

`pixi run pytest tests/ -m "not integration" -v`

这项测试可以稳定地触发创建`output_dir`的现象。

于是就开一个终端不停地运行这条测试，不断把出现的文件夹删除。

线索：

1. 创建文件夹的时候是有创建时间的；
2. ProcMon在上面的配置下（加上打开最顶上那一行的各种Show，总之能捕捉的全捕捉），可以捕捉到数个相关日志，关闭Typora和Explorer等无关项目，发现剩下的只有`python.exe`，也就是说并不是IDE之类的东西，而确实就是程序本身创建的。
3. 其中有一条捕捉到的信息，和出现的文件夹的创建时间在同一秒，定位为怀疑对象。
4. 将procmon给出的stack信息发给Qwen（更新在chat记录里了），但AI表示在这边好像抓不住，还是要用钩子代码。

1:39 周六

有点累，排查半天好像毫无进展。



