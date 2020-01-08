import torch
import torch.nn as nn
from torch.autograd import Variable 
import numpy as np

try:
    from torch.hub import load_state_dict_from_url
except ImportError:
    from torch.utils.model_zoo import load_url as load_state_dict_from_url


device = 'cuda' if torch.cuda.is_available() else 'cpu'

__all__ = ['BIO_Resnet', 'BIO_Resnet18', 'BIO_Resnet34', 'BIO_Resnet50', 'BIO_Resnet101',
           'BIO_Resnet152', 'resnext50_32x4d', 'resnext101_32x8d',
           'wide_BIO_Resnet50_2', 'wide_BIO_Resnet101_2']


model_urls = {
    'Resnet18': 'https://download.pytorch.org/models/Resnet18-5c106cde.pth',
    'Resnet34': 'https://download.pytorch.org/models/Resnet34-333f7ec4.pth',
    'Resnet50': 'https://download.pytorch.org/models/Resnet50-19c8e357.pth',
    'Resnet101': 'https://download.pytorch.org/models/Resnet101-5d3b4d8f.pth',
    'Resnet152': 'https://download.pytorch.org/models/Resnet152-b121ed2d.pth',
    'resnext50_32x4d': 'https://download.pytorch.org/models/resnext50_32x4d-7cdf4587.pth',
    'resnext101_32x8d': 'https://download.pytorch.org/models/resnext101_32x8d-8ba56ff5.pth',
    'wide_BIO_Resnet50_2': 'https://download.pytorch.org/models/wide_BIO_Resnet50_2-95faca4d.pth',
    'wide_BIO_Resnet101_2': 'https://download.pytorch.org/models/wide_BIO_Resnet101_2-32ee1156.pth',
}


def conv3x3(in_planes, out_planes, stride=1, groups=1, dilation=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=dilation, groups=groups, bias=False, dilation=dilation)


def conv1x1(in_planes, out_planes, stride=1):
    """1x1 convolution"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, bias=False)


def depth_channel_computer(no_blocks = 3,
                           no_students = 4,
                           original_channels = [128,256,512]
                           ):

    Depth_channels_list = []

    if no_blocks==1:
        for j in range(no_students):
            Depth_channels_list.append([original_channels[0],
                                        original_channels[1],
                                        int(original_channels[2]*(float(no_students-j)/no_students))
                                        ])
    
    elif no_blocks==2:
        for j in range(no_students):
            Depth_channels_list.append([original_channels[0],
                                        int(original_channels[1]*(float(no_students-j)/no_students)),
                                        int(original_channels[2]*(float(no_students-j)/no_students))
                                        ])       

    elif no_blocks==3:
        for j in range(no_students):
            Depth_channels_list.append([int(original_channels[0]*(float(no_students-j)/no_students)),
                                        int(original_channels[1]*(float(no_students-j)/no_students)),
                                        int(original_channels[2]*(float(no_students-j)/no_students))
                                        ])    

    else:
        raise IndexError("No blocks can only be 1,2 or 3")

    return Depth_channels_list


class BasicBlock(nn.Module):
    expansion = 1
    __constants__ = ['downsample']

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(BasicBlock, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        if groups != 1 or base_width != 64:
            raise ValueError('BasicBlock only supports groups=1 and base_width=64')
        if dilation > 1:
            raise NotImplementedError("Dilation > 1 not supported in BasicBlock")
        # Both self.conv1 and self.downsample layers downsample the input when stride != 1
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1 = norm_layer(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = norm_layer(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out


class Bottleneck(nn.Module):
    expansion = 4
    __constants__ = ['downsample']

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(Bottleneck, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        width = int(planes * (base_width / 64.)) * groups
        # Both self.conv2 and self.downsample layers downsample the input when stride != 1
        self.conv1 = conv1x1(inplanes, width)
        self.bn1 = norm_layer(width)
        self.conv2 = conv3x3(width, width, stride, groups, dilation)
        self.bn2 = norm_layer(width)
        self.conv3 = conv1x1(width, planes * self.expansion)
        self.bn3 = norm_layer(planes * self.expansion)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out

class Base_Resnet(nn.Module):

    # Common base model for all the Student models built on top of this 

    def __init__(self, block, layers, num_classes=1000, zero_init_residual=False,
                 groups=1, width_per_group=64, replace_stride_with_dilation=None,
                 norm_layer=None):

        super(Base_Resnet, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        self._norm_layer = norm_layer

        self.inplanes = 64
        self.dilation = 1
        if replace_stride_with_dilation is None:
            # each element in the tuple indicates if we should replace
            # the 2x2 stride with a dilated convolution instead
            replace_stride_with_dilation = [False, False, False]
        if len(replace_stride_with_dilation) != 3:
            raise ValueError("replace_stride_with_dilation should be None "
                             "or a 3-element tuple, got {}".format(replace_stride_with_dilation))
        self.groups = groups
        self.base_width = width_per_group
        self.conv1 = nn.Conv2d(3, self.inplanes, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = norm_layer(self.inplanes)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual block behaves like an identity.
        # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677

        if zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3.weight, 0)
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2.weight, 0)

    def _make_layer(self, block, planes, blocks, stride=1, dilate=False):
        norm_layer = self._norm_layer
        downsample = None
        previous_dilation = self.dilation
        if dilate:
            self.dilation *= stride
            stride = 1
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                conv1x1(self.inplanes, planes * block.expansion, stride),
                norm_layer(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample, self.groups,
                            self.base_width, previous_dilation, norm_layer))
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes, groups=self.groups,
                                base_width=self.base_width, dilation=self.dilation,
                                norm_layer=norm_layer))

        return nn.Sequential(*layers)

    def _forward_impl(self, x):
        
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)

        return x

    def forward(self, x):
        return self._forward_impl(x)


class Resnet_Student(nn.Module):

    # This builds up student model assuming outputs from the Base ResNet model

    def __init__(self, block, layers, num_classes=1000, zero_init_residual=False,
                 groups=1, width_per_group=64, replace_stride_with_dilation=None,
                 norm_layer=None,
                 depth_channels = [128,256,512]
                 ):

        super(Resnet_Student, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        self._norm_layer = norm_layer

        self.inplanes = 64
        self.dilation = 1
        if replace_stride_with_dilation is None:
            # each element in the tuple indicates if we should replace
            # the 2x2 stride with a dilated convolution instead
            replace_stride_with_dilation = [False, False, False]
        if len(replace_stride_with_dilation) != 3:
            raise ValueError("replace_stride_with_dilation should be None "
                             "or a 3-element tuple, got {}".format(replace_stride_with_dilation))
        self.groups = groups
        self.base_width = width_per_group

        self.layer2 = self._make_layer(block, depth_channels[0], layers[1], stride=2,
                                       dilate=replace_stride_with_dilation[0])
        self.layer3 = self._make_layer(block, depth_channels[1], layers[2], stride=2,
                                       dilate=replace_stride_with_dilation[1])
        self.layer4 = self._make_layer(block, depth_channels[2], layers[3], stride=2,
                                       dilate=replace_stride_with_dilation[2])
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(depth_channels[2] * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual block behaves like an identity.
        # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677
        if zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3.weight, 0)
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2.weight, 0)

    def _make_layer(self, block, planes, blocks, stride=1, dilate=False):
        norm_layer = self._norm_layer
        downsample = None
        previous_dilation = self.dilation
        if dilate:
            self.dilation *= stride
            stride = 1
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                conv1x1(self.inplanes, planes * block.expansion, stride),
                norm_layer(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample, self.groups,
                            self.base_width, previous_dilation, norm_layer))
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes, groups=self.groups,
                                base_width=self.base_width, dilation=self.dilation,
                                norm_layer=norm_layer))

        return nn.Sequential(*layers)

    def _forward_impl(self, x):
        # See note [TorchScript super()]

        x1 = self.layer2(x)
        x2 = self.layer3(x1)
        x3 = self.layer4(x2)

        x_out = self.avgpool(x3)
        x_out = torch.flatten(x_out, 1)
        x_out = self.fc(x_out)

        return x_out,[x1,x2,x3]

    def forward(self, x):
        return self._forward_impl(x)


class BIO_Resnet(nn.Module):

    # Overall resnet student framework buiding function which integrates base resnet with 
    # Student Resnet models

    def __init__(self, block, layers, num_classes=1000, zero_init_residual=False,
                 groups=1, width_per_group=64, replace_stride_with_dilation=None,
                 norm_layer=None,
                 Base_freeze= False,
                 no_students = 4,
                 no_blocks = 3,        # Select only from 3,2,1                 
                 ):

        super(BIO_Resnet, self).__init__()

        Depth_channels_list = depth_channel_computer(no_blocks=no_blocks,no_students=no_students)
        self.no_students = no_students
        self.no_blocks = no_blocks

        # Initializing the common base resent model

        self.Base_Resnet = Base_Resnet(block=block,layers=layers, num_classes=num_classes, zero_init_residual=False,
                                       groups=1, width_per_group=64, replace_stride_with_dilation=None,
                                       norm_layer=None,)

        self.Base_Resnet = self.Base_Resnet.to(device)

        if Base_freeze:
            self.base_freezer()

        # Initializing student models

        self.student_models = []

        for depth_channels in Depth_channels_list:
            Student_M = Resnet_Student(block=block,layers=layers, num_classes=num_classes, 
                                                      zero_init_residual=False,
                                                      groups=1, 
                                                      width_per_group=64, 
                                                      replace_stride_with_dilation=None,
                                                      norm_layer=None,
                                                      depth_channels=depth_channels)

            self.student_models.append(Student_M.to(device))

        # Initializing contribution weights for teacher output

        self.weights = Variable(torch.Tensor((float(1)/self.no_students)*np.ones([1,self.no_students,1])),
                                requires_grad= True).to(device)

    def base_freezer(self):

        for m in self.Base_Resnet.parameters():
            if m.requires_grad:
                m.requires_grad = False

    def _forward_impl(self, x):

        x = self.Base_Resnet(x)

        Student_final_outs = []
        Student_intermmediate_reps = [[] for _ in range(self.no_blocks)]

        for i in range(self.no_students):
            Final_out,Inter_reps = self.student_models[i](x)
            Student_final_outs.append(Final_out)
            if i==0:
                Combined_student_outs = Final_out.unsqueeze(1)
            else:
                Combined_student_outs = torch.cat((Combined_student_outs,Final_out.unsqueeze(1)),dim=1) # Combined_student_outs shape : (Batch_size, num_classes) 

            for j in range(self.no_blocks):
                Student_intermmediate_reps[j].append(Inter_reps[j])

        Teacher_out = torch.sum(Combined_student_outs,dim=1).squeeze(1)               # Teacher out shape : (Batch_size, num_classes)

        Student_final_outs = [Teacher_out] + Student_final_outs           

        return Student_final_outs,Student_intermmediate_reps

    def forward(self, x):
        return self._forward_impl(x)


def pretrained_weight_formatter(Arch,progress):

    base_weights = dict()

    if Arch == "Resnet18":
        Overall_model_dict = torch.load("../models/pretrained_weights/Resnet/resnet18.pth")
    
    for key in Overall_model_dict.keys():

        K = True
        for f in ["layer2","layer3","layer4","fc"]:
            if f in key:
                K = False
        
        if K:
            base_weights[key] = Overall_model_dict[key]

    return base_weights


def _BIO_Resnet(arch, block, layers, pretrained, progress,num_classes, **kwargs):

    model = BIO_Resnet(block, layers,num_classes=num_classes, **kwargs)

    if pretrained:
        state_dict = pretrained_weight_formatter(arch,progress)
        model.Base_Resnet.load_state_dict(state_dict)

    return model


def BIO_Resnet18(pretrained=False, progress=True,num_classes=1000, **kwargs):
    r"""BIO_Resnet-18 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _BIO_Resnet('Resnet18', BasicBlock, [2, 2, 2, 2], pretrained, progress,
                       num_classes=num_classes,**kwargs)


def BIO_Resnet34(pretrained=False, progress=True, **kwargs):
    r"""BIO_Resnet-34 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _BIO_Resnet('Resnet34', BasicBlock, [3, 4, 6, 3], pretrained, progress,
                   **kwargs)


def BIO_Resnet50(pretrained=False, progress=True, **kwargs):
    r"""BIO_Resnet-50 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _BIO_Resnet('Resnet50', Bottleneck, [3, 4, 6, 3], pretrained, progress,
                   **kwargs)


def BIO_Resnet101(pretrained=False, progress=True, **kwargs):
    r"""BIO_Resnet-101 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _BIO_Resnet('Resnet101', Bottleneck, [3, 4, 23, 3], pretrained, progress,
                   **kwargs)


def BIO_Resnet152(pretrained=False, progress=True, **kwargs):
    r"""BIO_Resnet-152 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _BIO_Resnet('Resnet152', Bottleneck, [3, 8, 36, 3], pretrained, progress,
                   **kwargs)


def resnext50_32x4d(pretrained=False, progress=True, **kwargs):
    r"""ResNeXt-50 32x4d model from
    `"Aggregated Residual Transformation for Deep Neural Networks" <https://arxiv.org/pdf/1611.05431.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['groups'] = 32
    kwargs['width_per_group'] = 4
    return _BIO_Resnet('resnext50_32x4d', Bottleneck, [3, 4, 6, 3],
                   pretrained, progress, **kwargs)


def resnext101_32x8d(pretrained=False, progress=True, **kwargs):
    r"""ResNeXt-101 32x8d model from
    `"Aggregated Residual Transformation for Deep Neural Networks" <https://arxiv.org/pdf/1611.05431.pdf>`_

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['groups'] = 32
    kwargs['width_per_group'] = 8
    return _BIO_Resnet('resnext101_32x8d', Bottleneck, [3, 4, 23, 3],
                   pretrained, progress, **kwargs)


def wide_BIO_Resnet50_2(pretrained=False, progress=True, **kwargs):
    r"""Wide BIO_Resnet-50-2 model from
    `"Wide Residual Networks" <https://arxiv.org/pdf/1605.07146.pdf>`_

    The model is the same as BIO_Resnet except for the bottleneck number of channels
    which is twice larger in every block. The number of channels in outer 1x1
    convolutions is the same, e.g. last block in BIO_Resnet-50 has 2048-512-2048
    channels, and in Wide BIO_Resnet-50-2 has 2048-1024-2048.

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['width_per_group'] = 64 * 2
    return _BIO_Resnet('wide_BIO_Resnet50_2', Bottleneck, [3, 4, 6, 3],
                   pretrained, progress, **kwargs)


def wide_BIO_Resnet101_2(pretrained=False, progress=True, **kwargs):
    r"""Wide BIO_Resnet-101-2 model from
    `"Wide Residual Networks" <https://arxiv.org/pdf/1605.07146.pdf>`_

    The model is the same as BIO_Resnet except for the bottleneck number of channels
    which is twice larger in every block. The number of channels in outer 1x1
    convolutions is the same, e.g. last block in BIO_Resnet-50 has 2048-512-2048
    channels, and in Wide BIO_Resnet-50-2 has 2048-1024-2048.

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['width_per_group'] = 64 * 2
    return _BIO_Resnet('wide_BIO_Resnet101_2', Bottleneck, [3, 4, 23, 3],
                   pretrained, progress, **kwargs)