from space import Space
from shape import Shape
from shape import shape_map
from space import ThreeDimensionSpace
import itertools


class InsertStructure2Space:

    def __init__(self, space: Space, random_strategy: str, need_insert_shape: dict, max_iter=1000) -> None:
        self.space = space
        self.random_strategy = random_strategy
        self.need_insert_shape = need_insert_shape
        self.shape_list = []
        self.max_iter = max_iter
        self.shape_num_dict = {}
        self.total_shape_num = 0
        self.current_shape_num_dict = 0

        # 设置插入形状个数
        self.set_insert_num()

    def insert_shape(self) -> None:
        #### 先不考虑重叠的情况，生成所有个数结构
        # 第一步，利用 halton 生成所有结构（total_shape_num）个数的结构质心（position）,
        # 这里直接调用 generate_halton_points 函数
        positions = self.space.generate_halton_points(self.total_shape_num)
        positions_iterator = iter(positions)
        # 第二步，为每一个 position 生成一个结构，并先存储到一个列表，并设置网格或者八叉树
        for shape_name in self.shape_num_dict.keys():
            new_shape = shape_map[shape_name].random_generate(self.space, next(positions), self.need_insert_shape[shape_name], self.random_strategy)
            if new_shape != None:
                self.shape_list.append(new_shape)
                self.current_shape_num_dict[shape_name] += 1
                # TODO 更新网格或者八叉树
                pass

        #### 使用网格或者八叉树检测重叠，如果重叠删除其中的形状，更新 shape_list、current_shape_num_dict 以及网格或者八叉树
        # 可以逐个检查是否和其他结构是否有碰撞，如果有直接删掉这一个结构
        shape_to_remove = []
        for shape in self.shape_list:
            if self.check_collision(shape):
                shape_to_remove.append(shape)

        # 删除结构
        for shape in shape_to_remove:
            self.shape_list.pop(shape)
            self.current_shape_num_dict[shape.get_type()] -= 1
            # TODO 更新网格或者八叉树
            pass

        #### 为删除的形状添加新的，这里随机生成位置，通过 current_shape_num_dict 判断每个形状缺失的个数
        # 这里添加时针对每个结构进行的，设置最大迭代次数，如果没插入成功，就报错
        for shape_name in self.shape_num_dict.keys():
            shape_num = self.shape_num_dict[shape_name] - self.current_shape_num_dict[shape_name]
            for i in range(shape_num):
                iter_num = 0
                while (iter_num < self.max_iter):
                    # 生成一个新的质心，并随机生成一个形状
                    random_position = self.space.random_point()
                    new_shape = shape_map[shape_name].random_generate(self.space, random_position, self.need_insert_shape[shape_name], self.random_strategy)

                    # 检测生成的结构是否为空（超出边界）是否和其他形状有碰撞（通过网格或者八叉树）
                    if new_shape != None and not self.check_collision(new_shape):
                        self.shape_list.append(new_shape)
                        self.current_shape_num_dict[shape_name] += 1
                        # TODO 更新网格或者八叉树
                        pass
                        break
                    else:
                        iter_num += 1

                # 插入失败，报错
                if iter_num == self.max_iter:
                    raise ValueError("Insert shape failed, please check the insert strategy and the space.")

        print("Compelete!")

    def check_collision(self, shape: 'Shape'):
        # 检测一个结构是否和其他结构重叠，
        # 这里可以先得到这个结构的邻居，
        # 然后判断邻居是否重叠得到结果
        # 这个函数只需要判断是否重叠仅可

        # TODO 第一步，得到所有邻居
        neighbor_shapes = []

        # 第二步，比较是否碰撞
        for neighbor in neighbor_shapes:
            # 判断包围盒是否碰撞，如果没有碰撞，就不用检测了
            if not shape.check_box_collision(neighbor):
                continue
            # 如果包围盒碰撞了，再检测两个形状是否碰撞
            elif shape.collide_with(neighbor, self.space):
                return True

        # 如果都没有碰撞，返回False
        return False

    def set_insert_num(self):
        for shape_name in self.need_insert_shape.keys():
            self.shape_num_dict[shape_name] = int((self.need_insert_shape[shape_name]['volume_fraction'] * self.space.get_volume()) / shape_map[shape_name].get_volumn())
            self.total_shape_num += self.shape_num_dict[shape_name]
            self.current_shape_num_dict[shape_name] = 0

    def shape2csv(self, file_path: str) -> None:
        raise NotImplementedError("shape2csv not implemented")

    def visualize(self) -> None:
        raise NotImplementedError("visualize not implemented")


if __name__ == '__main__':
    pass
    # 1. 设置生成随机化方式（可能有一些随机的，有一些固定的），随机化方式也有选择，以及空间维度大小
    # 2. 生成空间对象
    # 3. 生成对象插入空间对象InsertStructure2Space
    # 4. 在InsertStructure2Space对象中调用生成策略，并通过调用判断重叠策略来确定是否重叠, 然后生成一堆结构体对象，储存
    # 5. 调用visualize来可视化或者储存结果
    input_para = {
        "grid_dim": [128, 128, 128],
        "random_strategy": "random or parallel",
        "need_insert_shape": {
            "sphere": {
                "volume_fraction": 0.02,
                "radius": 5.0,
            },
            "sphere_shell": {
                "volume_fraction": 0.05,
                "radius": 2.0,
                "shell_thickness": 1.0,
            },
            "cylinder": {
                "volume_fraction": 0.02,
                "radius": 1.0,
                "height": 40.0,
            },
        },
        "max_iter": 1000,
    }

    nx = 126, ny = 126, nz = 126
    three_dimension_space = ThreeDimensionSpace(input_para["grid_dim"][0], input_para["grid_dim"][1], input_para["grid_dim"][2])
    insertStructure2Space = InsertStructure2Space(three_dimension_space, input_para["random_strategy"], input_para['need_insert_shape'], input_para['max_iter'])
    insertStructure2Space.insert_shape()
    insertStructure2Space.shape2csv("result.csv")
    insertStructure2Space.visualize()
