#!/usr/bin/python3
import csv
import argparse
import itertools
import math
import numpy as np
from torch.utils.data import DataLoader
import torchvision.utils as vutils
from torchvision.models import vgg16
from perceptual import LossNetwork
from datasets2 import  TrainDatasetFromFolder4,TrainDatasetFromFolder2,TestDatasetFromFolder1

from ECLoss import DCLoss
import torch.nn.functional as F
from skimage.metrics import structural_similarity as ski_ssim
from CAPLOSS import *
from GFN20 import *
# from model11242 import *
from FFA02 import ffa
from Labloss import LabLoss
from utils21 import *
import os


parser = argparse.ArgumentParser()
parser.add_argument('--epoch', type=int, default=0, help='starting epoch')
parser.add_argument('--n_epochs', type=int, default=20, help='number of epochs of training')
parser.add_argument('--batchSize', type=int, default=1, help='size of the batches')
#parser.add_argument('--dataroot', type=str, default='/home/omnisky/volume/datacyclegan', help='root directory of the dataset') #'datasets/horse2zebra/'
parser.add_argument('--lr', type=float, default=0.0001, help='initial learning rate')
#parser.add_argument('--decay_epoch', type=int, default=100, help='epoch to start linearly decaying the learning rate to 0')
#parser.add_argument('--size', type=int, default=256, help='size of the data crop (squared assumed)')
parser.add_argument('--input_nc', type=int, default=3, help='number of channels of input data')#256
parser.add_argument('--output_nc', type=int, default=3, help='number of channels of output data')
parser.add_argument('--cuda', action='store_true', default='Ture',help='use GPU computation')
parser.add_argument('--n_cpu', type=int, default=1, help='number of cpu threads to use during batch generation')
opt = parser.parse_args()
print(opt)

if torch.cuda.is_available() and not opt.cuda:
    print("WARNING: You have a CUDA device, so you should probably run with --cuda")

###### Definition of variables ######
# Networks
netG_content=Net_content()
netG_haze = Net_hazy()
net_dehaze  = ffa(3,5)
net_G= Net_G()


netG_content.cuda()
netG_haze.cuda()
net_dehaze.cuda()
net_G.cuda()


# Lossess
criterion_GAN = torch.nn.MSELoss()
criterion_cycle = torch.nn.L1Loss()
criterion_identity = torch.nn.L1Loss()

vgg_model = vgg16(pretrained=True).features[:16]
vgg_model = vgg_model.cuda()
for param in vgg_model.parameters():
     param.requires_grad = False

loss_network = LossNetwork(vgg_model).cuda()
loss_network.eval()


optimizer_G= torch.optim.Adam(itertools.chain(netG_content.parameters() ,net_dehaze.parameters(),netG_haze.parameters(),net_G.parameters()),  lr=opt.lr, betas=(0.5, 0.999))

lr_scheduler_G = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer_G, T_max=100)
dataloader1 = DataLoader(TrainDatasetFromFolder2('trainset/trainA_new',
                                     'trainset/trainB_new',  'trainset/trainB_newsize_128',crop_size= 128), batch_size=opt.batchSize,shuffle=True )  #SIDMS   /home/omnisky/volume/ITSV2/clear
# dataloader2 = DataLoader(TrainDatasetFromFolder4('/home/omnisky/4t/RESIDE/OTS_BETA/clear/clear_newsize',
#                                              '/home/omnisky/4t/RESIDE/OTS_BETA/haze/hazy7',  '/home/omnisky/4t/realWorldHazeDataSet/trainA_newsize_128', crop_size=128), batch_size=opt.batchSize,shuffle=True )  #SIDMS   /home/omnisky/volume/ITSV2/clear


val_data_loader = DataLoader(TestDatasetFromFolder1('testdataset'),
                       batch_size=opt.batchSize, shuffle=False, num_workers=opt.n_cpu)

logger1 = Logger(opt.n_epochs, len(dataloader1))
# logger2 = Logger(opt.n_epochs, len(dataloader1))
###################################
if not os.path.exists('output'):
    os.makedirs('output')
if not os.path.exists('./results'):
    os.makedirs('./results/Inputs')
    os.makedirs('./results/Outputs')
    os.makedirs('./results/Targets')
###### Training ######
for epoch in range(opt.epoch, opt.n_epochs):

    # if not epoch%2 :
    #     dataloader = dataloader1
    # else :
    #     dataloader = dataloader2
    
    dataloader = dataloader1
    

    ite = 0
    adjust_learning_rate(optimizer_G, epoch)

    for i, batch in enumerate(dataloader):

        # Set model input
      real_A = Variable(batch['A']).cuda(0)#clear
      real_B = Variable(batch['B']).cuda(0)
      real_R = Variable(batch['R']).cuda(0)

      if real_A.size(1) == 3 and real_B.size(1) == 3:
        ite += 1
        optimizer_G.zero_grad()
        content_B,con_B = netG_content(real_B)
        haze_mask_B,mask_B = netG_haze(real_B)

        content_R,con_R = netG_content(real_R)
        haze_mask_R,mask_R = netG_haze(real_R)

        recover_R = net_G(content_R, haze_mask_R)
        recover_B = net_G(content_B, haze_mask_B)

        meta_B = cat([con_B,mask_B],1)
        meta_R = cat([con_R, mask_R], 1)

        dehaze_B = net_dehaze(real_B, meta_B)
        dehaze_R = net_dehaze(real_R, meta_R)

        content_dehaze_R,con_dehaze_R = netG_content(dehaze_R)
        content_dehaze_B,con_dehaze_B = netG_content(dehaze_B)

        haze_mask_dehaze_R,mask_dehaze_B = netG_haze(dehaze_R)
        haze_mask_dehaze_B,mask_dehaze_R = netG_haze(dehaze_B)


        recover_dehaze_R = net_G(content_dehaze_R, haze_mask_dehaze_R)
        recover_dehaze_B = net_G(content_dehaze_B, haze_mask_dehaze_B)

       
        content_A ,con_A= netG_content(real_A)
        haze_mask_A,mask_A = netG_haze(real_A)

        meta_A = cat([con_A, mask_A],1)

        dehaze_A = net_dehaze(real_A, meta_A )
        recover_A = net_G(content_A, haze_mask_A)

        fake_hazy_A = net_G(content_A,haze_mask_B)

        content_fake_hazy_A, con_fake_hazy_A  = netG_content(fake_hazy_A )
        haze_mask_fake_hazy_A,mask_fake_hazy_A = netG_haze(fake_hazy_A )

        meta_fake_hazy_A = cat([con_fake_hazy_A,mask_fake_hazy_A],1)

        dehaze_fake_hazy_A = net_dehaze(fake_hazy_A, meta_fake_hazy_A )

      
        loss_haze =  F.smooth_l1_loss(fake_hazy_A , real_B)  + loss_network(fake_hazy_A , real_B) * 0.04

        loss_dehaze = F.smooth_l1_loss(dehaze_B, real_A)  + loss_network(dehaze_B, real_A) * 0.04 \
                      + F.smooth_l1_loss(dehaze_A, real_A)  + loss_network(dehaze_A, real_A) * 0.04 \
                       + F.smooth_l1_loss( dehaze_fake_hazy_A, real_A) + loss_network( dehaze_fake_hazy_A, real_A) * 0.04\
                   

        loss_content = F.smooth_l1_loss(content_A, content_B)  + F.smooth_l1_loss(content_dehaze_B, content_B) + F.smooth_l1_loss(content_dehaze_R, content_R)\
                        +F.smooth_l1_loss(content_fake_hazy_A ,content_A) # +F.smooth_l1_loss(content_A,content_dehaze_fake_B)\

        loss_mask = F.smooth_l1_loss(haze_mask_dehaze_B, haze_mask_A) + F.smooth_l1_loss(haze_mask_fake_hazy_A , haze_mask_B)#+ F.smooth_l1_loss(haze_mask_fake_hazy_A, haze_mask_A)


        loss_recover = F.smooth_l1_loss(recover_B, real_B) + loss_network(recover_B, real_B) * 0.04 + \
                       F.smooth_l1_loss(recover_A, real_A) + loss_network(recover_A, real_A) * 0.04 + \
                       F.smooth_l1_loss(recover_R, real_R) + loss_network(recover_R, real_R) * 0.04 + \
                       F.smooth_l1_loss(recover_dehaze_B, real_A) + loss_network(recover_dehaze_B, real_A) * 0.04

        y = dehaze_R
        z = dehaze_B
        tv_loss = (torch.sum(torch.abs(y[:, :, :, :-1] - y[:, :, :, 1:])) +
                   torch.sum(torch.abs(y[:, :, :-1, :] - y[:, :, 1:, :])))+\
                  (torch.sum(torch.abs(z[:, :, :, :-1] - z[:, :, :, 1:])) +
                   torch.sum(torch.abs(z[:, :, :-1, :] - z[:, :, 1:, :])))

        loss_DC_A = DCLoss((dehaze_R + 1) / 2, 16) + DCLoss((dehaze_B + 1) / 2, 16)  + DCLoss((dehaze_A  + 1) / 2, 16) + DCLoss((dehaze_fake_hazy_A  + 1) / 2, 16)
        loss_CAP = CAPLoss(dehaze_R)+CAPLoss(dehaze_B) + CAPLoss(dehaze_A) + CAPLoss(dehaze_fake_hazy_A)
        loss_Lab = LabLoss(dehaze_R, real_R)*0.01+LabLoss(dehaze_B,real_A)+LabLoss(dehaze_fake_hazy_A ,real_A)
        loss_Lab = loss_Lab.float()

        # Total loss
        loss_G = loss_recover +loss_content +loss_haze +loss_mask +10*loss_dehaze + 0.01 * loss_DC_A+ 2*1e-7*tv_loss + 0.001 *loss_CAP +0.0001*loss_Lab
        loss_G.backward()
        optimizer_G.step()

        ###################################

        # if not epoch % 2:
        #     logger = logger1
        # else :
        #     logger = logger2
        
        logger = logger1
        logger.log({'loss_G': loss_G,  'loss_recover': loss_recover,  'loss_content': loss_content, 'loss_mask': loss_mask, 'loss_haze': loss_haze, 'loss_dehaze': loss_dehaze,'tv_loss': tv_loss,'loss_DC_A': loss_DC_A, 'loss_CAP': loss_CAP, 'loss_Lab': loss_Lab})
        if ite % 1000 == 0:

            vutils.save_image(recover_R.data, './recover_R.png' , normalize=True)
            vutils.save_image(recover_B.data, './recover_B.png', normalize=True)

        if ite % 100 == 0:
            vutils.save_image(real_A.data, './real_A.png' , normalize=True)
            vutils.save_image(real_B.data, './real_B.png', normalize=True)
            vutils.save_image(real_R.data, './real_R.png', normalize=True)
            vutils.save_image(dehaze_B.data, './dehaze_B.png', normalize=True)
            vutils.save_image(dehaze_R.data, './dehaze_R.png' , normalize=True)
        

    # Update learning rates

    lr_scheduler_G.step()


    torch.save(netG_content.state_dict(), 'output/netG_content_%d.pth' % int(epoch+1))
    torch.save(netG_haze.state_dict(), 'output/netG_haze_%d.pth' % int(epoch+1))
    torch.save(net_dehaze.state_dict(), 'output/net_dehaze_%d.pth' % int(epoch + 1))
    torch.save(net_G.state_dict(), 'output/net_G_%d.pth' % int(epoch + 1))

    if epoch % 1 == 0:
        with torch.no_grad():
            print('------------------------')
            test_psnr = 0
            test_ssim = 0
            eps = 1e-10
            test_ite = 0
            # for image_name,input, target in enumerate(self.val_loader):
            for i, batch in enumerate(val_data_loader):
                # Set model input
                real_A = Variable(batch['A']).cuda(0)  # clear
                real_B = Variable(batch['B']).cuda(0)

                content_B,con_B= netG_content(real_B)
                hazy_mask_B ,mask_B= netG_haze(real_B)

                meta_B = cat([con_B,mask_B],1)
                dehaze_B = net_dehaze(real_B, meta_B)

                vutils.save_image(real_A.data, './results/Targets/%05d.png' % (int(i)), padding=0,
                                  normalize=True)  # False
                vutils.save_image(real_B.data, './results/Inputs/%05d.png' % (int(i)), padding=0, normalize=True)
                vutils.save_image(dehaze_B.data, './results/Outputs/%05d.png' % (int(i)), padding=0, normalize=True)
                # Calculation of SSIM and PSNR values
                # print(output)
                output = dehaze_B.data.cpu().numpy()[0]
                output[output > 1] = 1
                output[output < 0] = 0
                output = output.transpose((1, 2, 0))
                hr_patch = real_A.data.cpu().numpy()[0]
                hr_patch[hr_patch > 1] = 1
                hr_patch[hr_patch < 0] = 0
                hr_patch = hr_patch.transpose((1, 2, 0))
                # SSIM
                test_ssim += ski_ssim(output, hr_patch, data_range=1, multichannel=True)
                # PSNR
                imdf = (output - hr_patch) ** 2
                mse = np.mean(imdf) + eps
                test_psnr += 10 * math.log10(1.0 / mse)
                test_ite += 1
            test_psnr /= (test_ite)
            test_ssim /= (test_ite)
            print('Valid PSNR: {:.4f}'.format(test_psnr))
            print('Valid SSIM: {:.4f}'.format(test_ssim))
            f = open('PSNR.txt', 'a')
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow([epoch, test_psnr, test_ssim])
            f.close()
            print('------------------------')

###################################
