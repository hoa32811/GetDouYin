import os


def extract_thumnail():
	vidoe_extension = '.mp4'
	image_extension = '.png'
	current_folder = os.getcwd()
	# Remove all png file

	for i in os.listdir(current_folder):
		if i.endswith(image_extension):
			os.remove(os.path.join(current_folder, i))
	for i in os.listdir(current_folder):
		if i.endswith(vidoe_extension):
			os.system('ffmpeg -i {} -r 1 -f image2 {}-%3d{}'.format(i, i.replace(vidoe_extension, ''), image_extension))



if __name__ == '__main__':
	extract_thumnail()